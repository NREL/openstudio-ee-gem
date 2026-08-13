import json
import re


def _clean_text(raw):
    if raw is None:
        return None
    txt = str(raw).strip()
    if txt == "":
        return None
    if txt.lower() in {"nan", "null", "none", "not_applied", "not applied"}:
        return None
    return txt


def _safe_float(raw):
    try:
        return float(raw)
    except Exception:
        return None


def _cf_to_m3(value):
    val = _safe_float(value)
    return None if val is None else val * 0.028316846592


def _ft_to_m(value):
    val = _safe_float(value)
    return None if val is None else val * 0.3048


def parse_materials_payload(raw):
    txt = _clean_text(raw)
    if not txt:
        return []
    try:
        parsed = json.loads(txt)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def material_metrics_from_entry(entry):
    area_m2 = None
    volume_m3 = None
    length_m = None
    thickness_m = _ft_to_m(entry.get("rsmeans_thickness_ft"))

    quantity_si = _safe_float(entry.get("quantity_si"))
    unit_si = str(entry.get("unit_si", "")).strip().lower()
    if quantity_si is not None:
        if unit_si == "m2":
            area_m2 = quantity_si
        elif unit_si == "m3":
            volume_m3 = quantity_si
        elif unit_si == "m":
            length_m = quantity_si

    if volume_m3 is None:
        unit_volume = str(entry.get("unit_volume", "")).strip().lower()
        if unit_volume == "cf":
            volume_m3 = _cf_to_m3(entry.get("quantity_volume"))

    return volume_m3, area_m2, thickness_m, length_m


def component_from_entry(measure_name, entry):
    name = str(entry.get("name", "")).strip().lower()
    description = str(entry.get("description", "")).strip().lower()

    if measure_name == "wall":
        return "Wall insulation"
    if measure_name == "roof":
        return "Roof insulation"
    if measure_name == "window":
        if "secondary glazing" in name or "secondary glazing" in description:
            return "Secondary glazing"
        if "window frame" in name or "frame" in description:
            return "Window frame"
        if "film" in name or "film" in description:
            return "Glazing film"
        if "weatherstrip" in name or "weatherstrip" in description:
            return "Window weatherstrip"
        if "sealant" in name or "caulking" in description:
            return "Window caulking"
        if "glazing" in name or "pane" in description:
            return "Window glazing"
        return "Window material"
    if measure_name == "door":
        if "bottom" in name or "bottom" in description:
            return "Door bottom seal"
        if any(token in (name + " " + description) for token in ["top", "side", "jamb"]):
            return "Door top/side seal"
        if "door" in name or "door" in description:
            return "Door panel"
        return "Door material"
    return "Material"


def extract_material_type_name(name_str):
    """
    Extract material type name from entry name field.
    Examples:
      "Fiberglass Batts insulation" -> "Fiberglass Batts"
      "Blown Fiberglass roof insulation (Typical Uninsulated Wood Joist Attic Roof)" -> "Blown Fiberglass"
      "wood window frame" -> "wood window frame"
    """
    if not name_str:
        return name_str
    txt = str(name_str).strip()
    txt = re.sub(r"\s*\([^)]*\).*$", "", txt)
    txt = re.sub(r"\s+(roof\s+)?insulation\s*$", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s+retrofit\s*$", "", txt, flags=re.IGNORECASE)
    return txt.strip()


def build_material_list_row_html(
    scenario_display,
    component,
    material_name,
    volume_m3,
    area_m2,
    thickness_m,
    length_m,
    thermal_conductivity,
    density,
    lifetime_years,
):
    return (
        f"<tr><td>{scenario_display}</td><td>{component}</td><td>{material_name}</td>"
        f"<td>{volume_m3}</td><td>{area_m2}</td><td>{thickness_m}</td><td>{length_m}</td>"
        f"<td>{thermal_conductivity}</td><td>{density}</td><td>{lifetime_years}</td></tr>"
    )


def build_report_html(
    embodied_analysis_period_years,
    renovation_rows,
    energy_analysis_table,
    max_cost_class,
    money,
    max_cost_delta,
    max_cost_delta_pct,
    max_savings_scenario,
    max_emis_class,
    num,
    max_emis_delta,
    max_emis_delta_pct,
    max_emissions_scenario,
    min_construction_cost_text,
    min_construction_cost_scenario,
    min_embodied_text,
    min_embodied_intensity_text,
    min_embodied_scenario,
    lowest_cost_payback_text,
    lowest_cost_payback_scenario,
    lowest_carbon_payback_text,
    lowest_carbon_payback_scenario,
    spider_table_rows,
    baseline_cost_w,
    baseline_cost_value,
    b,
    best_cost_w,
    max_savings,
    baseline_emis_w,
    baseline_emis_value,
    best_emis_w,
    max_emissions_reduction,
    cost_payback_chart_rows,
    carbon_payback_chart_rows,
    material_list_section_html,
    material_comparison_section_html,
    generated_time,
    report_year,
    run_name,
    spider_chart_embed_html="",
    result_summary_pie_charts_html="",
):
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SCOPE Retrofit Measure Analysis Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background-color: #f5f5f5; }}
        .container {{ max-width: 900px; margin: 0 auto; background-color: white; padding: 40px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        .header {{ border-bottom: 3px solid #1f4788; padding-bottom: 20px; margin-bottom: 30px; }}
        h1 {{ color: #1f4788; font-size: 28px; margin-bottom: 5px; }}
        .subtitle {{ color: #666; font-size: 14px; margin-top: 5px; }}
        h2 {{ color: #1f4788; font-size: 18px; margin-top: 30px; margin-bottom: 15px; border-left: 4px solid #1f4788; padding-left: 10px; }}
        h3 {{ color: #1f4788; font-size: 15px; margin-top: 15px; margin-bottom: 10px; }}
        .section {{ margin-bottom: 30px; }}
        .summary-box {{ background-color: #e8f0f8; border-left: 4px solid #1f4788; padding: 15px; margin-bottom: 20px; border-radius: 3px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th {{ background-color: #1f4788; color: white; padding: 12px; text-align: left; font-weight: bold; border: 1px solid #ddd; }}
        td {{ padding: 10px 12px; border: 1px solid #ddd; }}
        .renovation-table th:first-child,
        .renovation-table td:first-child {{ white-space: nowrap; min-width: 100px; }}
        .material-costs-table th:first-child,
        .material-costs-table td:first-child {{ white-space: nowrap; min-width: 100px; }}
        .material-list-table {{ table-layout: fixed; width: 100%; }}
        .material-list-table th,
        .material-list-table td {{ font-size: 11px; padding: 6px 8px; word-break: break-word; }}
        .material-list-table th:first-child,
        .material-list-table td:first-child {{ min-width: 72px; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .metric-box {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }}
        .metric-card {{ background-color: #f9f9f9; border: 1px solid #ddd; padding: 15px; border-radius: 5px; text-align: center; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #1f4788; margin: 10px 0; }}
        .metric-label {{ font-size: 12px; color: #666; }}
        .positive {{ color: #28a745; font-weight: bold; }}
        .viz-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px; }}
        .chart-card {{ border: 1px solid #ddd; border-radius: 6px; padding: 15px; background: #fafafa; }}
        .chart-title {{ font-size: 14px; font-weight: 600; color: #1f4788; margin-bottom: 10px; }}
        .bar-chart {{ display: grid; gap: 10px; }}
        .bar-row {{ display: grid; grid-template-columns: 130px 1fr 80px; align-items: center; gap: 10px; }}
        .bar-label {{ font-size: 12px; color: #444; }}
        .bar-label.has-tip {{ position: relative; cursor: help; border-bottom: 1px dotted #1f4788; display: inline-block; }}
        .scenario-tip {{ display: none; position: absolute; z-index: 50; left: 0; top: 100%; margin-top: 6px; width: 320px; max-height: 260px; overflow-y: auto; background: #fff; border: 1px solid #1f4788; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.18); padding: 10px; font-size: 11px; color: #333; line-height: 1.5; text-align: left; white-space: normal; }}
        .scenario-tip-title {{ font-weight: 600; color: #1f4788; margin-bottom: 6px; }}
        .bar-label.has-tip:hover .scenario-tip {{ display: block; }}
        .bar-track {{ height: 12px; background: #e6e6e6; border-radius: 6px; overflow: hidden; }}
        .bar {{ height: 100%; border-radius: 6px; }}
        .bar.baseline {{ background: #6c757d; }}
        .bar.retrofit {{ background: #28a745; }}
        .bar-value {{ font-size: 12px; color: #333; text-align: right; white-space: nowrap; }}
        .legend {{ display: flex; gap: 12px; margin-top: 10px; font-size: 12px; color: #555; flex-wrap: wrap; }}
        .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
        .legend-swatch {{ width: 12px; height: 12px; border-radius: 3px; }}
        .stacked-chart {{ display: grid; gap: 10px; margin-top: 10px; }}
        .stacked-row {{ display: grid; grid-template-columns: 130px 1fr 120px; align-items: center; gap: 10px; }}
        .stacked-label {{ font-size: 12px; color: #444; }}
        .stacked-track {{ display: flex; height: 14px; background: #e6e6e6; border-radius: 7px; overflow: hidden; }}
        .stacked-segment {{ height: 100%; }}
        .stacked-segment.embodied {{ background: #fd7e14; }}
        .stacked-segment.operational {{ background: #007bff; }}
        .stacked-value {{ font-size: 12px; color: #333; text-align: right; white-space: nowrap; }}
        .iframe-wrap {{ border: 1px solid #ddd; border-radius: 6px; overflow: hidden; background: #fff; margin-top: 10px; }}
        .iframe-wrap iframe {{ width: 100%; height: 520px; border: 0; }}
        .scenario-pie-grid {{ display: grid; grid-template-columns: 1fr; gap: 16px; margin: 10px 0 16px 0; }}
        .scenario-pie-card {{ border: 1px solid #ddd; border-radius: 6px; background: #fafafa; padding: 12px; }}
        .scenario-pie-title {{ font-size: 14px; font-weight: 600; color: #1f4788; margin-bottom: 10px; }}
        .scenario-pie-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
        .scenario-pie-panel {{ border: 1px solid #e4e4e4; border-radius: 6px; background: #fff; padding: 10px; }}
        .scenario-pie-panel h4 {{ font-size: 12px; color: #1f4788; margin-bottom: 8px; }}
        .scenario-pie-wrap {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
        .scenario-pie {{ width: 110px; height: 110px; border-radius: 50%; border: 1px solid #ddd; flex: 0 0 110px; }}
        .scenario-pie-legend {{ flex: 1 1 180px; font-size: 12px; color: #333; display: grid; gap: 5px; }}
        .scenario-pie-legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
        .scenario-pie-swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
        .scenario-pie-empty {{ font-size: 12px; color: #777; font-style: italic; }}
        .scenario-pie-total {{ margin-top: 8px; font-size: 11px; color: #666; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #999; font-size: 12px; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SCOPE Retrofit Measure Analysis Report</h1>
            <div class="subtitle">Comprehensive Energy and Financial Analysis</div>
        </div>

        <div class="section">
            <h2>Executive Summary</h2>
            <div class="summary-box">
                <p>This report compares energy consumption and operational costs between baseline and all applied renovation scenarios from CSV results. Embodied carbon is annualized using an analysis period of {embodied_analysis_period_years:g} years, while operational carbon is reported over 1 year. The construction cost data is from {report_year} RSMeans Database. The embodied carbon is calculated using data from EC3 Environmental Product Declaration (EPD) Database. Since RSMeans Database is proprietary, users can adopt customized cost dataset when needed.</p>
            </div>
            <h3>Renovation Details by Scenario</h3>
            <table class="renovation-table">
                <tr><th>Scenario</th><th>Renovation Type</th><th>Renovation Details</th></tr>
                {renovation_rows}
            </table>
        </div>

        <div class="section">
            <h2>Annual Energy Analysis</h2>
            <table>
                <tr><th>Scenario</th><th>Metric</th><th>Baseline</th><th>Renovation</th><th>Delta</th><th>Savings %</th></tr>
                {energy_analysis_table}
            </table>
        </div>

        <div class="section">
            <h2>Key Performance Metrics</h2>
            <div class="metric-box">
                <div class="chart-card">
                    <div class="chart-title">Operational Cost Saving (Scenario - Baseline) ($/yr) Comparison</div>
                    <div class="bar-chart">
                        <div class="bar-row">
                            <div class="bar-label">Baseline</div>
                            <div class="bar-track"><div class="bar baseline" style="width: {baseline_cost_w:.1f}%;"></div></div>
                            <div class="bar-value">{money(baseline_cost_value)}</div>
                        </div>
                        <div class="bar-row">
                            <div class="bar-label">{max_savings_scenario}</div>
                            <div class="bar-track"><div class="bar retrofit" style="width: {best_cost_w:.1f}%;"></div></div>
                            <div class="bar-value">{money(max_savings['annual_cost_usd'])}</div>
                        </div>
                    </div>
                    <div class="legend">
                        <span class="legend-item"><span class="legend-swatch" style="background:#6c757d"></span>Baseline</span>
                        <span class="legend-item"><span class="legend-swatch" style="background:#28a745"></span>{max_savings_scenario}</span>
                    </div>
                    <p style="font-size:12px;color:#666;margin-top:8px;">Max saving: <span class="{max_cost_class}">{money(max_cost_delta)} ({num(max_cost_delta_pct)}%)</span></p>
                </div>
                <div class="chart-card">
                    <div class="chart-title">Operational Carbon Saving (Scenario - Baseline) (kg CO2e/yr) Comparison</div>
                    <div class="bar-chart">
                        <div class="bar-row">
                            <div class="bar-label">Baseline</div>
                            <div class="bar-track"><div class="bar baseline" style="width: {baseline_emis_w:.1f}%;"></div></div>
                            <div class="bar-value">{num(baseline_emis_value)}</div>
                        </div>
                        <div class="bar-row">
                            <div class="bar-label">{max_emissions_scenario}</div>
                            <div class="bar-track"><div class="bar retrofit" style="width: {best_emis_w:.1f}%;"></div></div>
                            <div class="bar-value">{num(max_emissions_reduction['annual_emissions_kg'])}</div>
                        </div>
                    </div>
                    <div class="legend">
                        <span class="legend-item"><span class="legend-swatch" style="background:#6c757d"></span>Baseline</span>
                        <span class="legend-item"><span class="legend-swatch" style="background:#28a745"></span>{max_emissions_scenario}</span>
                    </div>
                    <p style="font-size:12px;color:#666;margin-top:8px;">Max saving: <span class="{max_emis_class}">{num(max_emis_delta)} kgCO2e ({num(max_emis_delta_pct)}%)</span></p>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Min Retrofit Construction Cost</div>
                    <div class="metric-value">{min_construction_cost_text}</div>
                    <div style="font-size:12px;color:#666;">{min_construction_cost_scenario}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Min Retrofit Embodied Carbon</div>
                    <div class="metric-value">{min_embodied_text}</div>
                    <div style="font-size:12px;color:#666;">Embodied carbon intensity (ECI): {min_embodied_intensity_text}</div>
                    <div style="font-size:12px;color:#666;">{min_embodied_scenario}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Lowest Retrofit Cost Payback Period</div>
                    <div class="metric-value">{lowest_cost_payback_text}</div>
                    <div style="font-size:12px;color:#666;">{lowest_cost_payback_scenario}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Lowest Retrofit Carbon Payback Period</div>
                    <div class="metric-value">{lowest_carbon_payback_text}</div>
                    <div style="font-size:12px;color:#666;">{lowest_carbon_payback_scenario}</div>
            </div>
        </div>

        <div class="section">
            <h2>Comparative Visualizations between Renovation Scenarios</h2>
            <div class="chart-card" style="margin-top: 20px;">
                <div class="chart-title">Spider Chart Visualization</div>
                <div class="iframe-wrap">
                    {spider_chart_embed_html}\n
                </div>
            </div>

        </div>

        <div class="section" id="payback-section">
            <h2>Payback Period of the Retrofit</h2>
            <div class="viz-grid">
                <div class="chart-card">
                    <div class="chart-title">Cost Payback Period</div>
                    <p style="font-size:12px;color:#666;margin-bottom:8px;">Payback = retrofit construction cost / abs(Operational Cost Saving (Scenario - Baseline) ($/yr)).</p>
                    <div class="bar-chart">
                        {cost_payback_chart_rows}
                    </div>
                </div>

                <div class="chart-card">
                    <div class="chart-title">Carbon Payback Period</div>
                    <p style="font-size:12px;color:#666;margin-bottom:8px;">Payback = retrofit embodied carbon / abs(Operational Carbon Saving (Scenario - Baseline) (kg CO2e/yr)).</p>
                    <div class="bar-chart">
                        {carbon_payback_chart_rows}
                    </div>
                </div>
            </div>
        </div>

        {material_comparison_section_html}

        {material_list_section_html}

        <div class="section">
            <h2>Result Summary</h2>
            {result_summary_pie_charts_html}
            </div>
            <table class="material-costs-table">
                <tr><th>Scenario</th><th>Retrofit Embodied Carbon (kgCO2e)</th><th>Retrofit Construction Cost (USD)</th><th>Annual Operational Carbon (kgCO2e)</th><th>Annual Operational Cost (USD)</th></tr>
                {spider_table_rows}

            </table>
        </div>

        <div class="footer">
            <p>Generated: {generated_time} | Report Type: Retrofit Impact Analysis | Run: {run_name}</p>
        </div>
    </div>
    <script>
    (function () {{
        var table = document.querySelector('table.renovation-table');
        var section = document.getElementById('payback-section');
        if (!table || !section) {{ return; }}
        var details = {{}};
        Array.prototype.forEach.call(table.querySelectorAll('tr'), function (row) {{
            var cells = row.querySelectorAll('td');
            if (cells.length < 3) {{ return; }}
            details[cells[0].textContent.trim()] = cells[2].innerHTML;
        }});
        Array.prototype.forEach.call(section.querySelectorAll('.bar-label'), function (label) {{
            var key = label.textContent.trim();
            if (!details[key]) {{ return; }}
            var tip = document.createElement('div');
            tip.className = 'scenario-tip';
            var title = document.createElement('div');
            title.className = 'scenario-tip-title';
            title.textContent = key + ' - Renovation Details';
            tip.appendChild(title);
            var body = document.createElement('div');
            body.innerHTML = details[key];
            tip.appendChild(body);
            label.classList.add('has-tip');
            label.appendChild(tip);
        }});
    }})();
    </script>
</body>
</html>
"""

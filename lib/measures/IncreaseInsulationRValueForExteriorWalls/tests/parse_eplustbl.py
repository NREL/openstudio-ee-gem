import re
import sys
from pathlib import Path
import pandas as pd

#!/usr/bin/env python3

def extract_field(pattern: str, html_text: str) -> str:
    """Extract text matching the pattern from HTML."""
    m = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else ""

def extract_building_string(html_text: str) -> str:
    # Primary: find text inside <b> tag after 'Building:'
    m = re.search(r'Building:\s*<b>([^<]+)</b>', html_text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback 1: text after 'Building:' up to next tag
    m2 = re.search(r'Building:\s*([^<\r\n]+)', html_text, flags=re.IGNORECASE)
    if m2:
        return m2.group(1).strip()
    # Fallback 2: strip tags and search line-based
    text = re.sub(r'<[^>]+>', '', html_text)
    m3 = re.search(r'Building:\s*(.+)', text, flags=re.IGNORECASE)
    return m3.group(1).strip() if m3 else ""

def extract_all_data(html_text: str) -> dict:
    """Extract all requested fields from EnergyPlus HTML report."""
    data = {}
    
    # Building name
    data["building_name"] = extract_building_string(html_text)
    
    # Environment: text inside <b> tag after 'Environment:'
    data["environment"] = extract_field(r'Environment:\s*<b>([^<]+)</b>', html_text)
    
    # Simulation hours: extract number from "Values gathered over X hours"
    hours_match = extract_field(r'Values gathered over\s+([0-9.]+)\s+hours', html_text)
    data["simulation_hours"] = hours_match if hours_match else ""
    
    # Site and Source Energy from the table
    # Total Site Energy
    data["total_site_energy_GJ"] = extract_field(
        r'Total Site Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
    
    # Net Site Energy
    data["net_site_energy_GJ"] = extract_field(
        r'Net Site Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
    
    # Total Source Energy
    data["total_source_energy_GJ"] = extract_field(
        r'Total Source Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
    
    # Net Source Energy
    data["net_source_energy_GJ"] = extract_field(
        r'Net Source Energy</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
    
    # Building Areas
    data["total_building_area_m2"] = extract_field(
        r'Total Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
    
    data["net_conditioned_building_area_m2"] = extract_field(
        r'Net Conditioned Building Area</td>\s*<td[^>]*>\s*([0-9.]+)', html_text)
    
    return data

def main():
    # Default file name
    default_file = "eplustbl.html"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(default_file)

    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    html = path.read_text(encoding="utf-8", errors="ignore")
    data = extract_all_data(html)
    
    # Create DataFrame
    df = pd.DataFrame([data])
    
    # Print to console
    print("\n" + "="*80)
    print("Extracted Data from EnergyPlus Report")
    print("="*80)
    print(df.to_string(index=False))
    print("="*80 + "\n")
    
    # Save CSV next to the HTML file
    csv_path = path.with_suffix('.summary.csv')
    df.to_csv(csv_path, index=False)
    print(f"CSV saved to: {csv_path.absolute()}\n")

if __name__ == "__main__":
    main()
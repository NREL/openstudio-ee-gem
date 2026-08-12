"""
Standalone script to fetch EPD data for window materials and organize into tables
"""

import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
import configparser

# Add the resources path to import EC3_lookup functions
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
resources_path = os.path.join(parent_dir, "lib", "measures", "window_enhancement", "resources")
sys.path.insert(0, resources_path)

from EC3_lookup import generate_url_byname, fetch_epd_data, parse_product_epd, extract_numeric_value

# Read API token
config_path = os.path.join(parent_dir, "config.ini")
if not os.path.exists(config_path):
    print(f"Error: Config file not found: {config_path}")
    print("Please create config.ini file in project root directory with format:")
    print("[EC3_API_TOKEN]")
    print("API_TOKEN = your_api_token_here")
    sys.exit(1)

config = configparser.ConfigParser()
config.read(config_path)

try:
    API_TOKEN = config["EC3_API_TOKEN"]["API_TOKEN"]
except KeyError:
    print("Error: Missing [EC3_API_TOKEN] or API_TOKEN in config.ini file")
    sys.exit(1)

# Define all window material types and their corresponding API query parameters
WINDOW_MATERIALS = {
    # Glass Pane Products
    "Processed Non-Insulating Glass Panes": {
        "category": "6daae3d967104f5c8c85199b259f58c8",
        "name_like": "monolithic glass",
        "plant_geography": "021",
        "component_type": "glass pane"
    },
    "Insulating Glazing Unit - Double Pane": {
        "name_like": "double pane",
        "plant_geography": "021",
        "component_type": "glass pane"
    },
    "Insulating Glazing Unit - Triple Pane": {
        "category": "ade3ad3405124279955e7d3085f59383",
        "name_like": "triple pane",
        "plant_geography": "021",
        "component_type": "glass pane"
    },
    
    # Window Frame Products
    "Wood Window Frame": {
        "name_like": "wood window frame",
        "plant_geography": "150",
        "component_type": "window frame"
    },
    "Wood-Aluminium Window Frame": {
        "name_like": "wood-aluminium window frame",
        "plant_geography": "150",
        "component_type": "window frame"
    },
    
    # Window Perimeter Caulking
    "Window Perimeter Caulking - Sealant Acrylic": {
        "name_like": "sealant",
        "description_like": "acrylic",
        "plant_geography": "021",
        "component_type": "window perimeter caulking"
    },
    "Window Perimeter Caulking - Single-Ply Polyurethane": {
        "category": "e95e0d13de844101beb364b47af73d45",
        "description_like": "window",
        "plant_geography": "021",
        "component_type": "window perimeter caulking"
    },
    
    # Window Film Products
    "Window Film - Safety Film": {
        "category": "3aa3a34fae9a400fa297339ba88e1fab",
        "name_like": "glazing",
        "description_like": "safety film",
        "plant_geography": "021",
        "component_type": "window film"
    },
    "Window Film - Solar Control Film": {
        "category": "3aa3a34fae9a400fa297339ba88e1fab",
        "name_like": "glazing",
        "description_like": "solar control film",
        "plant_geography": "021",
        "component_type": "window film"
    },
    "Window Film - Anti-Graffiti Film": {
        "category": "3aa3a34fae9a400fa297339ba88e1fab",
        "name_like": "glazing",
        "description_like": "anti-graffiti film",
        "plant_geography": "021",
        "component_type": "window film"
    },
    "Window Film - Decorative Film": {
        "category": "3aa3a34fae9a400fa297339ba88e1fab",
        "name_like": "glazing",
        "description_like": "decorative film",
        "plant_geography": "021",
        "component_type": "window film"
    },
    "Window Film - Low-E Film": {
        "category": "3aa3a34fae9a400fa297339ba88e1fab",
        "name_like": "glazing",
        "description_like": "low-e film",
        "plant_geography": "021",
        "component_type": "window film"
    },
    
    # Window Weatherstrip
    "Window Weatherstrip - Silicone Adhesive Smoke Gasket": {
        "category": "ca54e842c0fc4bf2b4f3a8564c3b1a4d",
        "name_like": "doors hardware",
        "description_like": "silicone adhesive smoke gasket",
        "plant_geography": "021",
        "component_type": "window weatherstrip"
    },
    
    # Whole Window Products
    "Fixed Window": {
        "name_like": "fixed window",
        "plant_geography": "021",
        "component_type": "whole window"
    },
    "Project Window": {
        "name_like": "project window",
        "plant_geography": "021",
        "component_type": "whole window"
    },
    "Sliding Window": {
        "name_like": "sliding window",
        "plant_geography": "021",
        "component_type": "whole window"
    },
    "Storefront Window": {
        "name_like": "storefront window",
        "plant_geography": "021",
        "component_type": "whole window"
    },
    "Casement Window": {
        "name_like": "casement window",
        "plant_geography": "021",
        "component_type": "whole window"
    },
    "Opening Window": {
        "name_like": "opening window",
        "plant_geography": "021",
        "component_type": "whole window"
    },
    "Outward Hinged Window": {
        "name_like": "open outward",
        "plant_geography": "021",
        "component_type": "whole window"
    }
}

def remove_outliers_iqr(data):
    """Remove outliers using IQR method"""
    if len(data) < 4:
        return data
    
    data_array = np.array(data)
    q1 = np.percentile(data_array, 25)
    q3 = np.percentile(data_array, 75)
    iqr = q3 - q1
    
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    
    filtered_data = [x for x in data if lower_bound <= x <= upper_bound]
    
    return filtered_data

def create_statistics_summary(df, timestamp, output_dir):
    """Create a CSV summary of box plot statistics (min, max, median, mean) for each metric by material type"""
    
    # Define metrics to analyze
    metrics = [
        {
            'column': 'density',
            'extract_func': lambda x: extract_numeric_value(x) if x and x != 'N/A' and x is not None else None
        },
        {
            'column': 'thickness_per_declared_unit',
            'extract_func': lambda x: extract_numeric_value(x) if x and x != 'N/A' and x is not None else None
        },
        {
            'column': 'reference_service_life',
            'extract_func': lambda x: extract_numeric_value(x) if x and x != '' and x != 'N/A' and x is not None else None
        },
        {
            'column': 'gwp_per_declared_unit',
            'extract_func': lambda x: extract_numeric_value(x) if x and x != 'N/A' and x is not None else None
        },
        {
            'column': 'gwp_per_kg (kg CO2 eq/kg)',
            'extract_func': lambda x: float(x) if x and x != 'N/A' and x != 0.0 and x is not None else None
        },
        {
            'column': 'gwp_per_m3 (kg CO2 eq/m3)',
            'extract_func': lambda x: float(x) if x and x != 'N/A' and x != 0.0 and x is not None else None
        },
        {
            'column': 'gwp_per_m2 (kg CO2 eq/m2)',
            'extract_func': lambda x: float(x) if x and x != 'N/A' and x != 0.0 and x is not None else None
        },
        {
            'column': 'gwp_per_unit (kg CO2 eq/unit)',
            'extract_func': lambda x: float(x) if x and x != 'N/A' and x != 0.0 and x is not None else None
        }
    ]
    
    summary_rows = []
    
    for metric in metrics:
        metric_name = metric['column']
        
        # Skip if column doesn't exist in DataFrame
        if metric_name not in df.columns:
            print(f"  ⚠ Skipping {metric_name} - column not found in DataFrame")
            continue
        
        for material in sorted(df['Material Category'].unique()):
            material_df = df[df['Material Category'] == material]
            
            # Extract numeric values
            values = []
            for val in material_df[metric['column']]:
                try:
                    numeric_val = metric['extract_func'](val)
                    if numeric_val is not None and not np.isnan(numeric_val):
                        values.append(numeric_val)
                except (ValueError, TypeError):
                    continue
            
            if values:
                # Calculate statistics
                summary_rows.append({
                    'Metric': metric_name,
                    'Material Category': material,
                    'Component Type': material_df['Component Type'].iloc[0],
                    'Count': len(values),
                    'Min': np.min(values),
                    'Max': np.max(values),
                    'Mean': np.mean(values),
                    'Median': np.median(values),
                    'Std Dev': np.std(values),
                    'Q1 (25th percentile)': np.percentile(values, 25),
                    'Q3 (75th percentile)': np.percentile(values, 75)
                })
    
    # Create DataFrame and save
    summary_df = pd.DataFrame(summary_rows)
    
    summary_filename = f"window_epd_statistics_summary_{timestamp}.csv"
    summary_filepath = os.path.join(output_dir, summary_filename)
    summary_df.to_csv(summary_filepath, index=False, encoding='utf-8-sig')
    
    print(f"✓ Statistical summary saved: {summary_filepath}")
    
    # Display sample
    print(f"\nSample Statistical Summary (first 10 rows):")
    print(summary_df.head(10).to_string(index=False))
    print(f"\nTotal rows in summary: {len(summary_df)}")

def calculate_statistics(values):
    """Calculate statistical data"""
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std": None
        }
    
    return {
        "count": len(values),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "std": float(np.std(values))
    }

def fetch_material_epd_data(material_name, query_params):
    """Fetch EPD data for a single material"""
    print(f"\n{'='*80}")
    print(f"Fetching material: {material_name}")
    print(f"Component Type: {query_params.get('component_type', 'N/A')}")
    print(f"{'='*80}")
    
    # Create a copy of query params without component_type for API call
    api_params = {k: v for k, v in query_params.items() if k != 'component_type'}
    
    # 生成API URL
    try:
        url = generate_url_byname(**api_params)
        print(f"API URL: {url}")
    except Exception as e:
        print(f"  ❌ Error generating URL: {e}")
        return None
    
    # Get EPD data with error handling
    try:
        epd_response = fetch_epd_data(url, API_TOKEN)
    except Exception as e:
        print(f"  ❌ Error fetching data: {e}")
        return None
    
    if not epd_response:
        print(f"  No data retrieved")
        return None
    
    # Save raw JSON response
    output_dir = os.path.join(script_dir, "window epd data")
    os.makedirs(output_dir, exist_ok=True)
    json_filename = f"{material_name.replace(' ', '_').replace('(', '').replace(')', '').replace('-', '_')}_raw_response.json"
    json_filepath = os.path.join(output_dir, json_filename)
    with open(json_filepath, 'w', encoding='utf-8') as f:
        json.dump(epd_response, f, indent=2, ensure_ascii=False)
    print(f"  ✓ JSON response saved: {json_filename}")
    
    # Parse response
    epds = []
    if isinstance(epd_response, dict) and 'results' in epd_response:
        epds = epd_response['results']
    elif isinstance(epd_response, list):
        epds = epd_response
    
    print(f"  Found {len(epds)} EPDs")
    
    # Store detailed information for all EPDs
    epd_details = []
    
    for idx, epd in enumerate(epds, start=1):
        parsed = parse_product_epd(epd)
        
        # Debug: Check what data looks like in raw EPD data
        if idx <= 3:  # Log first 3 EPDs for debugging
            print(f"  Debug EPD #{idx}: Product name = {parsed.get('product_name', 'N/A')}")
            print(f"  Debug EPD #{idx}: Declared unit = {parsed.get('declared_unit', 'N/A')}")
        
        # Add material category and component type to the parsed data
        parsed["Material Category"] = material_name
        parsed["Component Type"] = query_params.get('component_type', 'N/A')
        
        # Append the complete parsed data
        epd_details.append(parsed)
    
    print(f"  Processed {len(epd_details)} EPD records")
    
    return {
        "material_name": material_name,
        "component_type": query_params.get('component_type', 'N/A'),
        "total_epds": len(epds),
        "epd_details": epd_details
    }

def main():
    """Main function"""
    print(f"Starting Window EPD data retrieval...")
    print(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Create output directory if it doesn't exist
    output_dir = os.path.join(script_dir, "window epd data")
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}\n")
    
    all_results = []
    all_epd_details = []
    
    # Iterate through all materials
    for material_name, query_params in WINDOW_MATERIALS.items():
        try:
            result = fetch_material_epd_data(material_name, query_params)
            if result:
                all_results.append(result)
                all_epd_details.extend(result["epd_details"])
        except KeyboardInterrupt:
            print(f"\n⚠ Interrupted by user. Processing data collected so far...")
            break
        except Exception as e:
            print(f"\n❌ Error processing {material_name}: {e}")
            print(f"Continuing with next material...")
            continue
    
    # Create detailed EPD table
    print(f"\n{'='*80}")
    print("Generating detailed EPD table...")
    print(f"{'='*80}\n")
    
    if all_epd_details:
        details_df = pd.DataFrame(all_epd_details)
        
        # Save detailed EPD data
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        details_filename = f"window_epd_data_{timestamp}.csv"
        details_filepath = os.path.join(output_dir, details_filename)
        details_df.to_csv(details_filepath, index=False, encoding='utf-8-sig')
        print(f"✓ Detailed EPD data saved: {details_filepath}")
        
        # Generate statistical summary
        print(f"\n{'='*80}")
        print("Generating statistical summary...")
        print(f"{'='*80}\n")
        
        create_statistics_summary(details_df, timestamp, output_dir)
        
        # Display sample of data in console
        print(f"\n{'='*80}")
        print("Sample EPD Data (first 10 rows)")
        print(f"{'='*80}\n")
        
        # Set pandas display options for better table formatting
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        pd.set_option('display.max_colwidth', 40)
        
        print(details_df.head(10).to_string(index=False))
        
        # Print summary by material category
        print(f"\n{'='*80}")
        print("EPD Count by Material Category")
        print(f"{'='*80}\n")
        material_counts = details_df['Material Category'].value_counts().sort_index()
        for material, count in material_counts.items():
            print(f"  {material}: {count} EPDs")
        
        # Print summary by component type
        print(f"\n{'='*80}")
        print("EPD Count by Component Type")
        print(f"{'='*80}\n")
        component_counts = details_df['Component Type'].value_counts().sort_index()
        for component, count in component_counts.items():
            print(f"  {component}: {count} EPDs")
        
        print(f"\n{'='*80}")
        print("✓ All processing complete!")
        print(f"{'='*80}\n")
    else:
        print("⚠ No EPD data collected. Please check API parameters and connectivity.")

if __name__ == "__main__":
    main()

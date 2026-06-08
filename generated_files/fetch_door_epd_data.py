"""
Standalone script to fetch EPD data for door materials (sealing and whole doors) and organize into tables
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
resources_path = os.path.join(parent_dir, "lib", "measures", "door_enhancement", "resources")
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

# Define all door material types and their corresponding API query parameters
# Based on the table provided, organized by renovation type
DOOR_MATERIALS = {
    # Door Sealing Products
    "Silicone Adhesive Smoke Gasket": {
        "category": "ca54e842c0fc4bf2b4f3a8564c3b1a4d",
        "name_like": "silicone adhesive smoke gasket",
        "plant_geography": "021",
        "renovation_type": "door sealing"
    },
    "Brush Weatherstrip": {
        "category": "ca54e842c0fc4bf2b4f3a8564c3b1a4d",
        "name_like": "brush weatherstrip",
        "plant_geography": "021",
        "renovation_type": "door sealing"
    },
    "Automatic Door Bottom": {
        "category": "ca54e842c0fc4bf2b4f3a8564c3b1a4d",
        "name_like": "automatic door bottom",
        "plant_geography": "021",
        "renovation_type": "door sealing"
    },
    "Jamb Weatherstripping": {
        "name_like": "jamb weatherstripping",
        "plant_geography": "021",
        "renovation_type": "door sealing"
    },
    
    # Whole Door Products
    "Wood Door Leaf": {
        "name_like": "wood door leaf",
        "plant_geography": "021",
        "renovation_type": "whole door"
    },
    "Garage Door": {
        "name_like": "garage door",
        "plant_geography": "150",
        "renovation_type": "whole door"
    },
    "Window Door System": {
        "name_like": "window door system",
        "plant_geography": "150",
        "renovation_type": "whole door"
    },
    "Polystyrene Core Steel Door": {
        "name_like": "polystyrene core steel door",
        "plant_geography": "021",
        "renovation_type": "whole door"
    },
    "Polyurethane Core Steel Door": {
        "name_like": "polyurethane core steel door",
        "plant_geography": "021",
        "renovation_type": "whole door"
    },
    "Fiberglass Core": {
        "category": "73e602b930884f559e90418f35ee4ed",
        "name_like": "fiberglass core",
        "plant_geography": "021",
        "renovation_type": "whole door"
    },
    "Honeycomb Core Steel Door": {
        "name_like": "honeycomb core steel door",
        "plant_geography": "021",
        "renovation_type": "whole door"
    },
    "Stiffened Core": {
        "category": "e9605505973e4f088078c6f53e58129f",
        "name_like": "stiffened core",
        "plant_geography": "021",
        "renovation_type": "whole door"
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
        },
        {
            'column': 'gwp_per_m (kg CO2 eq/m)',
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
        
        # Debug: Check if we're processing reference_service_life
        if metric_name == 'reference_service_life':
            print(f"  Processing reference_service_life metric...")
            print(f"  Total rows in DataFrame: {len(df)}")
            print(f"  Non-null reference_service_life values: {df['reference_service_life'].notna().sum()}")
            print(f"  Sample values: {df['reference_service_life'].head(10).tolist()}")
        
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
                    'Renovation Type': material_df['Renovation Type'].iloc[0],
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
    
    summary_filename = f"door_epd_statistics_summary_{timestamp}.csv"
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
    print(f"Renovation Type: {query_params.get('renovation_type', 'N/A')}")
    print(f"{'='*80}")
    
    # Create a copy of query params without renovation_type for API call
    api_params = {k: v for k, v in query_params.items() if k != 'renovation_type'}
    
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
    output_dir = os.path.join(script_dir)
    os.makedirs(output_dir, exist_ok=True)
    json_filename = f"{material_name.replace(' ', '_').replace('(', '').replace(')', '')}_raw_response.json"
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
        
        # Add material category and renovation type to the parsed data
        parsed["Material Category"] = material_name
        parsed["Renovation Type"] = query_params.get('renovation_type', 'N/A')
        
        # Append the complete parsed data
        epd_details.append(parsed)
    
    print(f"  Processed {len(epd_details)} EPD records")
    
    return {
        "material_name": material_name,
        "renovation_type": query_params.get('renovation_type', 'N/A'),
        "total_epds": len(epds),
        "epd_details": epd_details
    }

def main():
    """Main function"""
    print(f"Starting Door EPD data retrieval...")
    print(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Create output directory if it doesn't exist
    output_dir = os.path.join(script_dir)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}\n")
    
    all_results = []
    all_epd_details = []
    
    # Iterate through all materials
    for material_name, query_params in DOOR_MATERIALS.items():
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
        output_dir = os.path.join(script_dir)
        details_filename = f"door_epd_data_{timestamp}.csv"
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
        
        # Print summary by renovation type
        print(f"\n{'='*80}")
        print("EPD Count by Renovation Type")
        print(f"{'='*80}\n")
        renovation_counts = details_df['Renovation Type'].value_counts().sort_index()
        for renovation_type, count in renovation_counts.items():
            print(f"  {renovation_type}: {count} EPDs")
    
    print(f"\n{'='*80}")
    print("Data retrieval completed!")
    print(f"Total materials processed: {len(all_results)}")
    print(f"Total EPDs retrieved: {len(all_epd_details)}")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()

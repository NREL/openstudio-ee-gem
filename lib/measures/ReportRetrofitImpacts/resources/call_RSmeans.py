import requests
from typing import Optional, Dict, Any
import json
import urllib3
from sys import argv
from dotenv import load_dotenv
import os
import openpyxl
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_division_from_material_type(material_type: str) -> Optional[str]:
    """
    Map material type to RSMeans MasterFormat division code.
    
    Args:
        material_type: Material type string (e.g., 'insulation', 'concrete', 'drywall')
    
    Returns:
        str: Two-digit division code (e.g., '07' for insulation) or None if not found
    """
    mapping = {
        # Division 03 - Concrete
        'concrete': '03',
        'footing': '03',
        'slab': '03',
        
        # Division 04 - Masonry
        'brick': '04',
        'masonry': '04',
        'block': '04',
        
        # Division 05 - Metals
        'steel': '05',
        'metal': '05',
        
        # Division 06 - Wood, Plastics, and Composites
        'wood': '06',
        'lumber': '06',
        
        # Division 07 - Thermal and Moisture Protection
        'insulation': '07',
        'roofing': '07',
        'waterproofing': '07',
        'sealant': '07',
        
        # Division 08 - Openings
        'door': '08',
        'window': '08',
        'glazing': '08',
        
        # Division 09 - Finishes
        'drywall': '09',
        'gypsum': '09',
        'paint': '09',
        'flooring': '09',
        'ceiling': '09',
        'tile': '09',
        
        # Division 22 - Plumbing
        'plumbing': '22',
        'pipe': '22',
        
        # Division 23 - HVAC
        'hvac': '23',
        'duct': '23',
        'boiler': '23',
        'chiller': '23',
        
        # Division 26 - Electrical
        'electrical': '26',
        'lighting': '26',
        'wiring': '26',
    }
    
    # Try exact match first, then partial match
    material_lower = material_type.lower().strip()
    
    if material_lower in mapping:
        return mapping[material_lower]
    
    # Try partial matching
    for key, division in mapping.items():
        if key in material_lower or material_lower in key:
            return division
    
    return None


class RSMeansAPIClient:
    """
    Client for interacting with the RSMeans Sandbox API.
    Handles authentication and data retrieval.
    """

    def __init__(self,
                client_id,
                client_secret,
                use_sandbox: bool = False):
        """
        Initialize the RSMeans API client with credentials.

        Args:
            use_sandbox: If True, use sandbox API; if False, use production API
        """
        # credentials
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = "https://login.gordian.com/connect/token"

        # Set API base URL based on environment
        if use_sandbox:
            self.base_url = "https://dataapi-sb.gordian.com"
        else:
            self.base_url = "https://dataapi.gordian.com"

        self.access_token = None
        self.token_type = None

    def authenticate(self) -> bool:
        """
        Authenticate with Gordian's Identity Server and retrieve access token.

        Returns:
            bool: True if authentication successful, False otherwise
        """
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'rsm_api:costdata'
        }

        try:
            # Disable SSL verification to handle certificate issues - for running on NREL laptop
            response = requests.post(self.token_url, data=data, verify=False)
            response.raise_for_status()

            token_data = response.json()
            self.access_token = token_data.get('access_token')
            self.token_type = token_data.get('token_type', 'Bearer')

            print("Authentication successful!")
            return True

        except requests.exceptions.RequestException as e:
            print(f"Authentication failed: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """
        Get headers with authorization token for API requests.

        Returns:
            dict: Headers including Bearer token
        """
        if not self.access_token:
            raise Exception("Not authenticated. Call authenticate() first.")

        return {
            'Authorization': f'{self.token_type} {self.access_token}',
            'Content-Type': 'application/json'
        }

    def get_cost_data_releases(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve available cost data releases (year or quarter)

        Returns:
            dict: JSON response with available releases
        """
        endpoint = f"{self.base_url}/v1/costdata/releases"

        try:
            response = requests.get(endpoint, headers=self._get_headers(), verify=False)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving cost data releases: {e}")
            return None

    def get_locations(self, release_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve available locations for cost data.

        Args:
            release_id: Optional release ID to filter locations

        Returns:
            dict: JSON response with available locations
        """
        endpoint = f"{self.base_url}/v1/costdata/locations"
        params = {}
        if release_id:
            params['releaseId'] = release_id

        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params, verify=False)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving locations: {e}")
            return None

    def get_unit_catalogs(self,
                        release_id: str,
                        location_id: str,
                        labor_type: str = "std",
                        measurement_system: str = "imp") -> Optional[Dict[str, Any]]:
        """
        Retrieve sll unit cost catalogs for given parameters.

        Args:
            release_id: Cost data release ID by year and split by annual or quarter.  [year]-[an|q1|q2|q3|q4]
            location_id: Location ID for cost localization. [country]-[state|province(2char)]-[city]
            labor_type: Labor type. [std]=standard union labor, [opn]=Open Shop, [fmr]=Facility Maintenance & Repair, [fed]=Federal, [he]=Higher Education
            measurement_system:  [met]=metric, [imp]=imperial

        Returns:
            dict: JSON response with catalog information
        """
        endpoint = f"{self.base_url}/v1/costdata/unit/catalogs"
        params = {
            'releaseId': release_id,
            'locationId': location_id,
            'laborType': labor_type,
            'measurementSystem': measurement_system
        }

        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params, verify=False)
            response.raise_for_status()
            print(f"Returning unit cost catalog options for {release_id} {location_id} {labor_type} {measurement_system}")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving unit catalogs: {e}")
            return None

    def search_unit_costlines(self,
                                release_id: str,
                                measurement_system: str,
                                searchTerm: str,
                                catalog: Optional[str] = 'bc-mf',
                                location_id: Optional[str] = 'us-us-national',
                                labor_type: Optional[str] = 'std',
                                divisionCode: Optional[str] = None
                                ) -> Optional[Dict[str, Any]]:
        """
        Search unit cost lines from a catalog using a keyword.

        Args:
            release_id: Catalog year and annual or quarterly basis [YYYY]-[an|q1|q2|q3|q4]
            measurement_system: [met]=metric, [imp]=imperial
            searchTerm: Item you'd like to seach for
            catalog: Catalog to retrieve lines from. Default is building construction masterformat
            location_id: Default is u.s. national data. Format [country]-[state|province]-[city] example: us-co-denver
            labor_type: [std]=standard union labor, [opn]=Open Shop, [fmr]=Facility Maintenance & Repair, [fed]=Federal, [he]=Higher Education

            divisionCode: the RSmeans line item code

        Returns:
            dict: JSON response with unit cost lines
        """
        catalog_id = f"{catalog}-{measurement_system}-{labor_type}-{release_id}-{location_id}"

        endpoint = f"{self.base_url}/v1/costdata/unit/catalogs/{catalog_id}/costlines/_search"
        params = {}
        if searchTerm:
            params['searchTerm'] = searchTerm
        if divisionCode:
            params['divisionCode'] = divisionCode
        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params, verify=False)
            response.raise_for_status()
            print (f"Returning unit cost line under {catalog_id} catalog, under division {divisionCode} with search term {searchTerm}")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving unit cost line: {e}")
            return None
        pass

    def get_unit_costlines(self,
                            release_id: str,
                            measurement_system: str,
                            divisionCode: str,
                            catalog: str = 'bc-mf',
                            location_id: str = 'us-us-national',
                            labor_type: str = 'std',

                            ) -> Optional[Dict[str, Any]]:
        """
        Retrieve unit cost lines from a catalog. this will return all the costs and crew hours associated with a single construction
        product. includes

        Args:
            release_id: a 4 digit year followed by 2 charecter designation of annual or quarterly '[year]-[annual(an)|q1|q2|q3|q4]'
            catalog: Catalog to retrieve lines from. default is building construction masterformat [bc-mf]
            location_id: [country]-[state|province(2char)]-[city]. Default is u.s. national data
            labor_type: [std]=standard union labor, [opn]=Open Shop, [fmr]=Facility Maintenance & Repair, [fed]=Federal, [he]=Higher Education
            measurement_system: [met]=metric, [imp]=imperial
            divisionCode: the line item code ex: '033053403920'

        Returns:
            dict: JSON response with unit cost lines
        """
        catalog_id = f"{catalog}-{measurement_system}-{labor_type}-{release_id}-{location_id}"

        endpoint = f"{self.base_url}/v1/costdata/unit/catalogs/{catalog_id}/costlines"
        params = {}
        if divisionCode:
            params['divisionCode'] = divisionCode

        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params, verify=False)
            response.raise_for_status()
            print (f"Returning unit cost line under {catalog_id}, division Code {divisionCode}")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving unit cost line: {e}")
            return None

    def get_unit_material_cost(self,
                                catalog_id: str,
                                ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a unit material cost including overhead and profit

        Args: catalog_id: Catalog ID to retrieve lines from
            division: Optional division to filter by (e.g., "01", "03")
            search_term: Optional search keyword
        """
        pass

    def search_materials_batch(self,
                               materials: list,
                               release_id: str = '2019-an',
                               catalog: str = 'bc-mf',
                               location_id: str = 'us-us-national',
                               labor_type: str = 'std',
                               measurement_system: str = 'imp',
                               save_search_results_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Search for multiple materials in RSMeans and return aggregated costs.

        Args:
            materials: List of material dicts with keys:
                      {'name': str, 'quantity': float, 'unit': str, 'division_code': str (optional)}
            release_id: Cost data release ID
            catalog: Catalog code
            location_id: Location for cost localization
            labor_type: Type of labor
            measurement_system: 'imp' for imperial, 'met' for metric
            save_search_results_path: Optional path to save raw search results JSON

        Returns:
            dict: Aggregated results with:
                  {'total_cost': float, 'materials': [{...}, ...], 'errors': [], 'search_log': []}
        """
        results = {
            'total_cost': 0.0,
            'materials': [],
            'errors': [],
            'search_log': []
        }

        for material in materials:
            material_name = material.get('name', '')
            quantity = material.get('quantity', 1.0)
            division_hint = material.get('division_code')

            if not material_name:
                results['errors'].append("Material name is required")
                continue

            # Auto-detect division if not provided
            if not division_hint:
                division_hint = get_division_from_material_type(material_name)
                if division_hint:
                    print(f"Auto-detected division {division_hint} for material: {material_name}")

            try:
                # Search for the material with optional division filter
                search_results = self.search_unit_costlines(
                    release_id=release_id,
                    measurement_system=measurement_system,
                    searchTerm=material_name,
                    catalog=catalog,
                    location_id=location_id,
                    labor_type=labor_type,
                    divisionCode=division_hint  # Use division filter if available
                )

                if not search_results or 'items' not in search_results or len(search_results['items']) == 0:
                    results['errors'].append(f"No RSMeans match found for: {material_name}")
                    continue

                # Get the first matching item
                first_item = search_results['items'][0]
                division_code = first_item.get('id')
                item_description = first_item.get('description', material_name)

                if not division_code:
                    results['errors'].append(f"No division code found for: {material_name}")
                    continue

                # Get detailed cost information
                cost_line = self.get_unit_costlines(
                    release_id=release_id,
                    catalog=catalog,
                    location_id=location_id,
                    labor_type=labor_type,
                    measurement_system=measurement_system,
                    divisionCode=division_code
                )

                # Log search results for debugging
                search_log_entry = {
                    'material_name': material_name,
                    'division_hint': division_hint,
                    'search_results_count': len(search_results.get('items', [])),
                    'division_code': division_code,
                    'first_match': first_item.get('description', ''),
                    'has_cost_data': cost_line is not None and 'items' in cost_line
                }
                results['search_log'].append(search_log_entry)

                if cost_line and 'items' in cost_line:
                    for item in cost_line['items']:
                        if item.get('id') == division_code:
                            unit_cost = item.get('localizedCosts', {}).get('totalOpCost', 0.0)
                            total_material_cost = unit_cost * quantity

                            results['materials'].append({
                                'name': material_name,
                                'description': item_description,
                                'division_code': division_code,
                                'unit_cost': unit_cost,
                                'quantity': quantity,
                                'total_cost': total_material_cost
                            })

                            results['total_cost'] += total_material_cost
                            break
                    else:
                        results['errors'].append(f"Division code not found in response: {division_code}")
                else:
                    results['errors'].append(f"No cost data returned for: {material_name}")

            except Exception as e:
                results['errors'].append(f"Error processing material '{material_name}': {str(e)}")
        
        # Save raw search results to JSON if path provided
        if save_search_results_path:
            try:
                import json
                from pathlib import Path
                output_path = Path(save_search_results_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2)
            except Exception as e:
                results['errors'].append(f"Could not save search results to JSON: {str(e)}")

        return results

    def get_unit_labor_cost():
        pass


if __name__ == "__main__":
    load_dotenv()
    client_id = os.getenv("client_id")
    client_secret = os.getenv("client_secret")

    if not client_id or not client_secret:
        print("RSMeans API credentials (client_id, client_secret) not found in environment.")
        raise SystemExit(1)

    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=False)
    if not client.authenticate():
        raise SystemExit(1)

    # Default materials to search
    default_materials = [
        {"name": "continuous strip footing", "quantity": 10.0, "unit": "C.Y."},
        {"name": "insulation", "quantity": 1260.0, "unit": "S.F."}
    ]

    output_path = Path(__file__).resolve().parent.parent / "Outputs" / "search_results.json"

    results = client.search_materials_batch(
        materials=default_materials,
        release_id="2025-q4",
        catalog="gb-mf",
        location_id="us-us-national",
        labor_type="std",
        measurement_system="imp",
        save_search_results_path=str(output_path)
    )

    print(f"\nSearch results saved to: {output_path}")
    print(f"Total cost: ${results.get('total_cost', 0.0):.2f}")
    
    if results.get('errors'):
        print(f"\nErrors encountered:")
        for error in results['errors']:
            print(f"  - {error}")
            materials=default_materials,
            release_id="2019-an",
            catalog="bc-mf",
            location_id="us-us-national",
            labor_type="std",
            measurement_system="imp",
            save_search_results_path=str(output_path)
        

        print(f"Processed search results saved to: {output_path}")
        print(f"Total cost: ${results.get('total_cost', 0.0):.2f}")



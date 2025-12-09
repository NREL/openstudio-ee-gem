import requests
from typing import Optional, Dict, Any
import json
import urllib3
from sys import argv
from dotenv import load_dotenv
import os
import openpyxl

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class RSMeansAPIClient:
    """
    Client for interacting with the RSMeans Sandbox API.
    Handles authentication and data retrieval.
    """

    def __init__(self,
                client_id,
                client_secret,
                use_sandbox: bool = True):
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

    def get_unit_labor_cost():
        pass

#==============================================================


# Example usage of this script (to be deleted for production)
def main():
    """
    Use of the RSMeans API client to find costs of construction items
    """
    #=========================================
    # Load credentials
    #=========================================
    load_dotenv()
    client_id = os.getenv('client_id')
    client_secret = os.getenv('client_secret')

    # Initialize client with credentials
    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=True)  # Set to False for production

    # Authenticate check
    if not client.authenticate():
        print("Failed to authenticate")
        return

    #==========================================
    # Examples of different functions
    #==========================================

    def available_cost_data_releases():
        # Example: Get available cost data releases
        print("\n=== Cost Data Releases available in API_responses folder @ releases.json ===")
        releases = client.get_cost_data_releases()
        if releases:
            with open("API_responses/release_versions.json", "w") as f:
                json.dumps(releases, f, indent=2)


    def available_locations():
        # retrieve all available locations and export results as json
        print("\n=== Locations ===")
        locations = client.get_locations()
        if locations:
            with open("API_responses/locations.json", "w") as f:
                json.dumps(locations, f, indent=2)


    def available_catalogs():
        # EXAMPLE: retrieve all available unit cost catalogs for a specific year, location, labor type and measurement system
        print("\n=== Retrieve all available unit cost catalogs for a specific year, location, labor type and measurement type " \
        "Return results in API_responses/catalogs.json")
        catalogs = client.get_unit_catalogs(
            release_id='2019-an',
            location_id='us-co-denver',
            labor_type= 'std',
            measurement_system= 'imp'
        )
        if catalogs:
            #print(json.dumps(catalogs, indent=2)[:500])# print first 500 char
            print ("saved as API_responses/catalogs.json")
            with open("API_responses/catalogs.json", "w") as f:
                json.dump(catalogs, f, indent=2)


    # EXAMPLE: Search for a product, return division codes
    print("\n=== Search for a product in a catalog. Return results in API_responses/search_unit_costlines.json ")

    search_for_unit = client.search_unit_costlines(
        release_id = '2019-an',
        measurement_system = 'imp',
        searchTerm = 'continuous strip footing'
    )
    if search_for_unit:
        # Save the JSON response to a file
        print ("saved as search_results.json")
        with open("API_responses/search_results.json", "w") as f:
            json.dump(unitcostline, f, indent=2)

    # EXAMPLE: Get unit cost line of a product from a catalog
    print("\n=== Retrieve the all of the unit cost information for a product in a catalog."
          " Return API_responses/unit_cost_line.json")
    unitcostline = client.get_unit_costlines(
        release_id = '2019-an',
        catalog = 'bc-mf',
        location_id = 'us-co-denver',
        labor_type = 'std',
        measurement_system = 'imp',
        divisionCode= '033053403920'
    )
    if unitcostline:
        #print(json.dumps(unitcostlines, indent=2)[:500]) )# print first 500 char
        # Save the JSON response to a file
        print ("saved under API_responses/unit_cost_line.json")
        with open("API_responses/unit_cost_line.json", "w") as f:
            json.dump(unitcostline, f, indent=2)

        #Extract totalOpCost and save to excel workbook
        total_op_cost =unitcostline.get("items", []).get("localizedCosts", {}).get("totalOpCost")
        item_description = unitcostline.get("items",[]).get("description")
        item_id = unitcostline.get("items", []).get("id")
        #load excel workbook
        excel_path = "resources/optimization_updated.xlsx"
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
        ws["B4"] = total_op_cost
        wb.save(excel_path)
        print(f"totalOpCost for {item_description} written to {excel_path} cell B4")
    else:
        print (f" item {item_description} with id number {item_id} not found or totalOpCost missing.")



if __name__ == "__main__":
    main()
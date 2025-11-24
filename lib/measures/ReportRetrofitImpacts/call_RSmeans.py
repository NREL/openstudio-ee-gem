import requests
from typing import Optional, Dict, Any
import json
import urllib3
from sys import argv
from dotenv import load_dotenv
import os

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

    def get_assembly_catalogs(self, release_id: str, location_id: str,
                              labor_type: str = "std",
                              measurement_system: str = "met") -> Optional[Dict[str, Any]]:
        """
        Retrieve assembly catalogs for given parameters.

        Args:
            release_id: Cost data release ID
            location_id: Location ID for cost localization
            labor_type: Labor type (e.g., "Standard Union", "Open Shop")
            measurement_system: "Imperial" or "Metric"

        Returns:
            dict: JSON response with catalog information
        """
        endpoint = f"{self.base_url}/v1/costdata/assembly/catalogs"
        params = {
            'releaseId': release_id,
            'locationId': location_id,
            'laborType': labor_type,
            'measurementSystem': measurement_system
        }

        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params, verify=False)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving assembly catalogs: {e}")
            return None

    def get_unit_catalogs(self, release_id: str, location_id: str,
                         labor_type: str = "std",
                         measurement_system: str = "imp") -> Optional[Dict[str, Any]]:
        """
        Retrieve unit cost catalogs for given parameters.

        Args:
            release_id: Cost data release ID year annual or quarter
            location_id: Location ID for cost localization
            labor_type: Labor type (e.g., "Standard Union"(std), "Open Shop"(opn))
            measurement_system: "Imperial" (imp) or "Metric" (met)

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

    def get_costdata_unit_costlines(self,
                                    catalog_id: str,
                                    divisionCode: Optional[str] = None,
                                    searchTerm: Optional[str] = None,
                                    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve unit cost lines from a catalog.

        Args:
            catalog_id: Catalog ID to retrieve lines from
            division: Optional division to filter by (e.g., "01", "03")
            search_term: Optional search keyword
            page: Page number (default 1)
            page_size: Number of records per page (default 100, max varies)

        Returns:
            dict: JSON response with unit cost lines
        """
        endpoint = f"{self.base_url}/v1/costdata/unit/catalogs/{catalog_id}/costlines"
        params = {}
        if divisionCode:
            params['divisionCode'] = divisionCode
        if searchTerm:
            params['searchTerm'] = searchTerm

        try:
            response = requests.get(endpoint, headers=self._get_headers(), params=params, verify=False)
            response.raise_for_status()
            print (f"Returning unit cost lines under {catalog_id}, division Code {divisionCode}, with search term {searchTerm} ")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error retrieving unit cost lines: {e}")
            return None

#==============================================================
# Example usage of this script (to be deleted for production)
def main():
    """
    Use of the RSMeans API client with NREL credentials.
    """
    #---------------------------------------------------------
    #load credentials

    load_dotenv()

    client_id = os.getenv('client_id')
    client_secret = os.getenv('client_secret')

    # Initialize client with credentials
    client = RSMeansAPIClient(client_id, client_secret, use_sandbox=True)  # Set to False for production

    # Authenticate check
    if not client.authenticate():
        print("Failed to authenticate")
        return
    #----------------------------------------------------------
    # Example: Get available cost data releases
    # print("\n=== Cost Data Releases ===")
    # releases = client.get_cost_data_releases()
    # if releases:
    #     print(json.dumps(releases, indent=2))

    # Example: Get locations
    # print("\n=== Locations ===")
    # locations = client.get_locations()
    # if locations:
    #     print(json.dumps(locations, indent=2)[:500])  # Print first 500 chars

    # Example: Get unit cost catalogs (need valid IDs from previous calls)
    print("\n=== Retrieve available unit cost catalogs for a specific year, location, labor type and measurement system")
    catalogs = client.get_unit_catalogs(
        release_id='2019-an',
        location_id='us-co-denver',
        labor_type= 'std',
        measurement_system= 'met'
    )
    if catalogs:

        #print(json.dumps(catalogs, indent=2)[:500])# print first 500 char
        print ("saved as catalogs.json")
        with open("catalogs.json", "w") as f:
            json.dump(catalogs, f, indent=2)

    # Example: Get unit cost catalogs (need valid IDs from previous calls)
    print("\n=== Retrieve unit cost lines for a specific product in a specific year, location, labor type and measurement system")
    unitcostlines = client.get_costdata_unit_costlines(
        catalog_id= 'bc-mf-imp-std-2019-an-us-co-denver',
        divisionCode= '03305340',
        searchTerm= None
    )
    if unitcostlines:
        #print(json.dumps(unitcostlines, indent=2)[:500]) )# print first 500 char
        # Save the JSON response to a file
        print ("saved as unit_cost_lines.json")
        with open("unit_cost_lines.json", "w") as f:
            json.dump(unitcostlines, f, indent=2)


if __name__ == "__main__":
    main()
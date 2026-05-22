import os
import json
import urllib.request
import urllib.error
import base64
from typing import Optional, Dict, Any

DATACITE_API_BASE_URL = os.getenv("DATACITE_API_URL", "https://api.test.datacite.org")
DATACITE_USER = os.getenv("DATACITE_USER")
DATACITE_PASSWORD = os.getenv("DATACITE_PASSWORD")
DATACITE_PREFIX = os.getenv("DATACITE_PREFIX")

class DataCiteClient:
    def __init__(self):
        if not all([DATACITE_USER, DATACITE_PASSWORD, DATACITE_PREFIX]):
            raise ValueError("Missing DataCite credentials or prefix env vars.")
        
        auth_str = f"{DATACITE_USER}:{DATACITE_PASSWORD}"
        self.auth_header = f"Basic {base64.b64encode(auth_str.encode()).decode()}"

    def _request(self, method: str, url: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/vnd.api+json",
            "Authorization": self.auth_header
        }
        
        json_data = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=json_data, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req) as response:
                if response.status == 204:
                    return {}
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"HTTP Error {e.code}: {error_body}")
            raise

    def create_draft_doi(self, metadata: Dict[str, Any]) -> str:
        """Creates a Draft DOI and returns the DOI string."""
        url = f"{DATACITE_API_BASE_URL}/dois"
        payload = {
            "data": {
                "type": "dois",
                "attributes": {
                    "prefix": DATACITE_PREFIX,
                    "event": "draft",
                    **metadata
                }
            }
        }
        result = self._request("POST", url, payload)
        return result["data"]["attributes"]["doi"]

    def update_doi(self, doi: str, attributes: Dict[str, Any]) -> None:
        """Updates an existing DOI's attributes."""
        url = f"{DATACITE_API_BASE_URL}/dois/{doi}"
        payload = {
            "data": {
                "type": "dois",
                "attributes": attributes
            }
        }
        self._request("PUT", url, payload)

    def publish_doi(self, doi: str, target_url: str) -> None:
        """Transitions a DOI from Draft to Findable state."""
        self.update_doi(doi, {"event": "publish", "url": target_url})

def map_stac_to_datacite(stac_item: Dict[str, Any], portal_ui_base_url: str) -> Dict[str, Any]:
    """Maps STAC metadata to DataCite attributes."""
    stac_id = stac_item.get("id")
    title = stac_item.get("title", stac_id)
    description = stac_item.get("description", "")
    created_at = stac_item.get("created")
    publication_year = created_at[:4] if created_at else "2026" # Default to current year or fallback
    
    # Extract creators/publishers from providers
    providers = stac_item.get("providers", [])
    creators = []
    publisher = "ESA Earthcode"
    
    for provider in providers:
        name = provider.get("name")
        roles = provider.get("roles", [])
        if "producer" in roles:
            creators.append({"name": name})
        if "host" in roles:
            publisher = name

    if not creators:
        creators = [{"name": "ESA Earthcode"}]

    resource_type = "Dataset" if stac_item.get("osc:type") == "product" else "Workflow"

    attributes = {
        "titles": [{"title": title}],
        "creators": creators,
        "publisher": publisher,
        "publicationYear": int(publication_year),
        "types": {
            "resourceTypeGeneral": resource_type,
            "resourceType": resource_type
        },
        "descriptions": [{"description": description, "descriptionType": "Abstract"}],
        "url": f"{portal_ui_base_url}/{stac_item.get('osc:type', 'products')}s/{stac_id}"
    }
    
    return attributes

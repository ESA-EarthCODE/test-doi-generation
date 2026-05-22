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
    """Maps STAC metadata to DataCite attributes including recommended properties."""
    stac_id = stac_item.get("id")
    title = stac_item.get("title", stac_id)
    description = stac_item.get("description", "")
    created_at = stac_item.get("created")
    updated_at = stac_item.get("updated")
    publication_year = created_at[:4] if created_at else "2026"
    
    # Extract creators/publishers/contributors from providers
    providers = stac_item.get("providers", [])
    creators = []
    contributors = []
    publisher = "ESA Earthcode"
    
    for provider in providers:
        name = provider.get("name")
        roles = provider.get("roles", [])
        # DataCite roles mapping
        if "producer" in roles:
            creators.append({"name": name, "nameType": "Organizational"})
        if "host" in roles:
            publisher = name
        if any(r in roles for r in ["licensor", "processor", "contributor"]):
            contributors.append({
                "name": name, 
                "nameType": "Organizational",
                "contributorType": "DataCollector" if "processor" in roles else "Distributor"
            })

    if not creators:
        creators = [{"name": "ESA Earthcode", "nameType": "Organizational"}]

    stac_type = stac_item.get("osc:type", "product")
    resource_type = "Dataset" if stac_type == "product" else "Workflow"
    suffix = "/collection" if stac_type == "product" else "/record"
    path_segment = f"{stac_type}s"

    # Subjects (Keywords)
    subjects = []
    for kw in stac_item.get("keywords", []):
        subjects.append({"subject": kw})

    # Dates
    dates = []
    if created_at:
        dates.append({"date": created_at, "dateType": "Created"})
    if updated_at:
        dates.append({"date": updated_at, "dateType": "Updated"})
    
    # Geolocations
    geolocations = []
    extent = stac_item.get("extent", {})
    spatial = extent.get("spatial", {})
    bboxes = spatial.get("bbox", [])
    if bboxes and isinstance(bboxes[0], list):
        for bbox in bboxes:
            if len(bbox) >= 4:
                geolocations.append({
                    "geoLocationBox": {
                        "westBoundLongitude": bbox[0],
                        "southBoundLatitude": bbox[1],
                        "eastBoundLongitude": bbox[2],
                        "northBoundLatitude": bbox[3]
                    }
                })

    # Related Identifiers (Links)
    related_identifiers = []
    for link in stac_item.get("links", []):
        rel = link.get("rel")
        href = link.get("href")
        if rel in ["cite-as", "via", "derived_from"] and href:
            # Try to detect if it's a DOI
            if "doi.org/" in href:
                doi_val = href.split("doi.org/")[-1]
                related_identifiers.append({
                    "relatedIdentifier": doi_val,
                    "relatedIdentifierType": "DOI",
                    "relationType": "IsDerivedFrom" if rel == "derived_from" else "IsDescribedBy"
                })
            else:
                related_identifiers.append({
                    "relatedIdentifier": href,
                    "relatedIdentifierType": "URL",
                    "relationType": "IsDerivedFrom" if rel == "derived_from" else "IsDescribedBy"
                })

    attributes = {
        "titles": [{"title": title}],
        "creators": creators,
        "contributors": contributors,
        "publisher": publisher,
        "publicationYear": int(publication_year),
        "subjects": subjects,
        "dates": dates,
        "language": "en",
        "types": {
            "resourceTypeGeneral": resource_type,
            "resourceType": resource_type
        },
        "descriptions": [{"description": description, "descriptionType": "Abstract"}],
        "geoLocations": geolocations,
        "relatedIdentifiers": related_identifiers,
        "url": f"{portal_ui_base_url}/{path_segment}/{stac_id}{suffix}"
    }
    
    return attributes

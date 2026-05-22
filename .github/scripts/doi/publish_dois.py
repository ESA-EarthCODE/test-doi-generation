import subprocess
import json
import os
import re
import sys

# Add the current script's directory to sys.path to allow importing sibling modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datacite import DataCiteClient

PORTAL_UI_BASE_URL = os.getenv("PORTAL_UI_BASE_URL", "https://catalog.earthcode.esa.int")

def get_modified_files_in_last_commit():
    """Returns a list of files modified in the last commit."""
    try:
        output = subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        return output.splitlines()
    except Exception:
        return []

def extract_doi_from_file(file_path):
    """Extracts sci:doi from a JSON file."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            return data.get("sci:doi"), data
    except Exception:
        return None, None

def main():
    try:
        client = DataCiteClient()
    except ValueError as e:
        print(f"Error: {e}")
        return

    files = get_modified_files_in_last_commit()
    published_count = 0

    for file_path in files:
        if file_path.endswith("collection.json") and ("products/" in file_path or "workflows/" in file_path):
            doi, stac_item = extract_doi_from_file(file_path)
            if doi:
                print(f"Publishing DOI {doi} for {file_path}")
                try:
                    # Construct target URL
                    stac_id = stac_item.get("id")
                    stac_type = stac_item.get("osc:type", "product")
                    target_url = f"{PORTAL_UI_BASE_URL}/{stac_type}s/{stac_id}"
                    
                    client.publish_doi(doi, target_url)
                    print(f"Successfully published {doi}")
                    published_count += 1
                except Exception as e:
                    print(f"Failed to publish {doi}: {e}")

    print(f"Finished. Published {published_count} DOIs.")

if __name__ == "__main__":
    main()

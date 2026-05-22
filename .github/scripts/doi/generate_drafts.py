import os
import json
import glob
import sys

# Add the current script's directory to sys.path to allow importing sibling modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datacite import DataCiteClient, map_stac_to_datacite
from check_changes import check_doi_need

SCIENTIFIC_EXTENSION_URL = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"
PORTAL_UI_BASE_URL = os.getenv("PORTAL_UI_BASE_URL", "https://opensciencedata.esa.int")

def main():
    try:
        client = DataCiteClient()
    except ValueError as e:
        print(f"Error: {e}")
        return

    # Find all products and workflows collection files
    files = glob.glob("products/**/collection.json", recursive=True) + \
            glob.glob("workflows/**/collection.json", recursive=True)

    summary = []
    modified_files = []

    for file_path in files:
        needs_doi, reason = check_doi_need(file_path)
        if needs_doi:
            print(f"Generating DOI for {file_path} (Reason: {reason})")
            
            with open(file_path, 'r') as f:
                stac_item = json.load(f)
            
            # Map metadata and create draft DOI
            metadata = map_stac_to_datacite(stac_item, PORTAL_UI_BASE_URL)
            try:
                doi = client.create_draft_doi(metadata)
                
                # Update STAC item
                stac_item["sci:doi"] = doi
                
                # Ensure scientific extension is present
                extensions = stac_item.get("stac_extensions", [])
                if SCIENTIFIC_EXTENSION_URL not in extensions:
                    extensions.append(SCIENTIFIC_EXTENSION_URL)
                    stac_item["stac_extensions"] = extensions
                
                with open(file_path, 'w') as f:
                    json.dump(stac_item, f, indent=4)
                
                summary.append(f"- {file_path}: {doi} (Reason: {reason})")
                modified_files.append(file_path)
            except Exception as e:
                print(f"Failed to create DOI for {file_path}: {e}")
                summary.append(f"- {file_path}: FAILED ({e})")

    if summary:
        print("\nDOI Generation Summary:")
        print("\n".join(summary))
        # Optional: write summary to a file for GitHub Action to read
        with open("doi_summary.md", "w") as f:
            f.write("## DOI Generation Summary\n\n")
            f.write("\n".join(summary))
    else:
        print("No DOIs needed to be generated.")

if __name__ == "__main__":
    main()

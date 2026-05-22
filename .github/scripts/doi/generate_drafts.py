import os
import json
import glob
import sys
import re

# Add the current script's directory to sys.path to allow importing sibling modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datacite import DataCiteClient, map_stac_to_datacite
from check_changes import check_doi_need

SCIENTIFIC_EXTENSION_URL = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"
PORTAL_UI_BASE_URL = os.getenv("PORTAL_UI_BASE_URL", "https://opensciencedata.esa.int")

def surgical_update(file_path: str, doi: str):
    """Updates the STAC collection or OGC Record file using string manipulation to preserve formatting."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    scientific_ext = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"
    is_record = file_path.endswith("record.json")
    
    # 1. Update/Insert sci:doi
    if '"sci:doi"' in content:
        # Update existing DOI value
        content = re.sub(r'("sci:doi"\s*:\s*")[^"]+(")', rf'\1{doi}\2', content)
    else:
        if is_record and '"properties"' in content:
            # Insert sci:doi inside properties
            # Find the properties block and its first key to match indentation
            match = re.search(r'("properties"\s*:\s*\{(\r?\n))(\s+)"', content)
            if match:
                prefix = match.group(1)
                indent = match.group(3)
                content = content.replace(prefix, f'{prefix}{indent}"sci:doi": "{doi}",\n')
            else:
                # Fallback: insert after {
                match = re.search(r'^(\s+)"', content, re.MULTILINE)
                indent = match.group(1) if match else "  "
                content = re.sub(r'^\{(\r?\n)', rf'{{\1{indent}"sci:doi": "{doi}",\1', content)
        else:
            # Insert sci:doi after the first { and its following newline
            match = re.search(r'^(\s+)"', content, re.MULTILINE)
            indent = match.group(1) if match else "  "
            content = re.sub(r'^\{(\r?\n)', rf'{{\1{indent}"sci:doi": "{doi}",\1', content)

    # 2. Update/Insert Extensions
    ext_key = "conformsTo" if is_record else "stac_extensions"
    if scientific_ext not in content:
        if f'"{ext_key}"' in content:
            # Find the array and append the new extension
            match = re.search(rf'("{ext_key}"\s*:\s*\[[^\]]*)', content, re.DOTALL)
            if match:
                prefix = match.group(1).rstrip()
                if prefix.strip().endswith('['):
                    new_ext = f'"{scientific_ext}"'
                else:
                    new_ext = f', "{scientific_ext}"'
                content = content.replace(match.group(1), prefix + new_ext)
        else:
            # Insert extension key after the first {
            match = re.search(r'^(\s+)"', content, re.MULTILINE)
            indent = match.group(1) if match else "  "
            ext_entry = f'{indent}"{ext_key}": [\n{indent}{indent}"{scientific_ext}"\n{indent}],\n'
            content = re.sub(r'^\{(\r?\n)', rf'{{\1{ext_entry}', content)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def main():
    try:
        client = DataCiteClient()
    except ValueError as e:
        print(f"Error: {e}")
        return

    # Find all products and workflows files
    files = glob.glob("products/**/collection.json", recursive=True) + \
            glob.glob("workflows/**/record.json", recursive=True)

    summary = []
    modified_files = []

    for file_path in files:
        needs_doi, reason = check_doi_need(file_path)
        if needs_doi:
            print(f"Generating DOI for {file_path} (Reason: {reason})")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                stac_item = json.load(f)
            
            # Map metadata and create draft DOI
            metadata = map_stac_to_datacite(stac_item, PORTAL_UI_BASE_URL)
            try:
                doi = client.create_draft_doi(metadata)
                
                # Surgically update the file to preserve formatting
                surgical_update(file_path, doi)
                
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

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
    prefix = os.environ.get("DATACITE_PREFIX")

    # 1. Handle Foreign DOI Migration
    if prefix and '"sci:doi"' in content:
        doi_match = re.search(r'"sci:doi"\s*:\s*"([^"]+)"', content)
        if doi_match:
            existing_val = doi_match.group(1)
            # If the current DOI is foreign (doesn't match our prefix)
            if not existing_val.startswith(prefix):
                print(f"Migrating foreign DOI {existing_val} to sci:publications")
                # Avoid adding it again if it's already there
                if f'"{existing_val}"' not in content or '"sci:publications"' not in content:
                    if '"sci:publications"' in content:
                        # Append to existing sci:publications array
                        pub_match = re.search(r'("sci:publications"\s*:\s*\[[^\]]*)', content, re.DOTALL)
                        if pub_match:
                            prefix_content = pub_match.group(1)
                            # Determine indentation
                            lines = prefix_content.split('\n')
                            indent = "    "
                            for line in reversed(lines):
                                if line.strip() and not line.strip().endswith('['):
                                    m = re.match(r'^(\s*)', line)
                                    if m:
                                        indent = m.group(1)
                                        break
                            
                            sep = "," if not prefix_content.strip().endswith("[") else ""
                            new_pub = f'{sep}\n{indent}{{"doi": "{existing_val}"}}'
                            content = content.replace(prefix_content, prefix_content + new_pub)
                    else:
                        # Create sci:publications array after the first {
                        match = re.search(r'^(\s+)"', content, re.MULTILINE)
                        indent = match.group(1) if match else "  "
                        pub_entry = f'{indent}"sci:publications": [\n{indent}{indent}{{"doi": "{existing_val}"}}\n{indent}],\n'
                        content = re.sub(r'^\{(\r?\n)', r'{\g<1>' + pub_entry, content)

    # 2. Update/Insert sci:doi
    if '"sci:doi"' in content:
        # Update existing DOI value
        # We use \g<1> and \g<2> to avoid ambiguity if the doi string starts with digits (e.g. \110 -> octal H)
        content = re.sub(r'("sci:doi"\s*:\s*")[^"]+(")', r'\g<1>' + doi + r'\g<2>', content)
    else:
        if is_record and '"properties"' in content:
            # Insert sci:doi inside properties
            # Find the properties block and its first key to match indentation
            match = re.search(r'("properties"\s*:\s*\{(\r?\n))(\s+)"', content)
            if match:
                prefix = match.group(1)
                indent = match.group(3)
                content = content.replace(prefix, prefix + indent + f'"sci:doi": "{doi}",\n')
            else:
                # Fallback: insert after {
                match = re.search(r'^(\s+)"', content, re.MULTILINE)
                indent = match.group(1) if match else "  "
                content = re.sub(r'^\{(\r?\n)', r'{\g<1>' + indent + f'"sci:doi": "{doi}",\n', content)
        else:
            # Insert sci:doi after the first { and its following newline
            match = re.search(r'^(\s+)"', content, re.MULTILINE)
            indent = match.group(1) if match else "  "
            content = re.sub(r'^\{(\r?\n)', r'{\g<1>' + indent + f'"sci:doi": "{doi}",\n', content)

    # 2. Update/Insert Extensions
    ext_key = "conformsTo" if is_record else "stac_extensions"
    if scientific_ext not in content:
        if f'"{ext_key}"' in content:
            # Find the array and append the new extension
            match = re.search(rf'("{ext_key}"\s*:\s*\[[^\]]*)', content, re.DOTALL)
            if match:
                prefix = match.group(1).rstrip()
                
                # Determine indentation for the new item
                lines = prefix.split('\n')
                item_indent = "    " # Default fallback
                for line in reversed(lines):
                    if line.strip() and not line.strip().endswith('['):
                        m = re.match(r'^(\s*)', line)
                        if m:
                            item_indent = m.group(1)
                            break
                            
                # Get the trailing whitespace to preserve closing bracket formatting
                trailing_ws_match = re.search(r'(\s+)$', match.group(1))
                trailing_ws = trailing_ws_match.group(1) if trailing_ws_match else "\n  "

                if prefix.strip().endswith('['):
                    new_ext = f'\n{item_indent}"{scientific_ext}"'
                else:
                    new_ext = f',\n{item_indent}"{scientific_ext}"'
                content = content.replace(match.group(1), prefix + new_ext + trailing_ws)
        else:
            # Insert extension key after the first {
            match = re.search(r'^(\s+)"', content, re.MULTILINE)
            indent = match.group(1) if match else "  "
            ext_entry = f'{indent}"{ext_key}": [\n{indent}{indent}"{scientific_ext}"\n{indent}],\n'
            content = re.sub(r'^\{(\r?\n)', r'{\g<1>' + ext_entry, content)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def main():
    try:
        client = DataCiteClient()
    except ValueError as e:
        print(f"Error: {e}")
        return

    changed_files_env = os.environ.get("CHANGED_FILES")
    
    if changed_files_env is not None:
        files = [f for f in changed_files_env.strip().split() if f]
        if not files:
            print("No relevant STAC Collections or OGC Records were modified in this PR. Skipping DOI generation.")
            return
        print(f"Running audit on modified files only: {files}")
    else:
        print("Running full repository audit...")
        files = glob.glob("products/**/collection.json", recursive=True) + \
                glob.glob("workflows/**/record.json", recursive=True)

    summary = []
    modified_files = []

    for file_path in files:
        needs_doi, reason = check_doi_need(file_path)
        if needs_doi:
            with open(file_path, 'r', encoding='utf-8') as f:
                stac_item = json.load(f)
            
            # Map metadata
            metadata = map_stac_to_datacite(stac_item, PORTAL_UI_BASE_URL)
            
            # Check if we should update or create
            existing_doi = stac_item.get("properties", stac_item).get("sci:doi")
            doi_to_use = None
            action = "created"

            if existing_doi:
                state = client.get_doi_state(existing_doi)
                if state == "draft":
                    print(f"Updating existing draft DOI {existing_doi} for {file_path}")
                    client.update_doi(existing_doi, metadata)
                    doi_to_use = existing_doi
                    action = "updated"
                else:
                    print(f"Existing DOI {existing_doi} is {state}. Creating a new version.")

            if not doi_to_use:
                print(f"Generating new DOI for {file_path} (Reason: {reason})")
                try:
                    doi_to_use = client.create_draft_doi(metadata)
                    # Surgically update the file to preserve formatting
                    surgical_update(file_path, doi_to_use)
                except Exception as e:
                    print(f"Failed to create DOI for {file_path}: {e}")
                    summary.append(f"- {file_path}: FAILED ({e})")
                    continue

            summary.append(f"- {file_path}: {doi_to_use} ({action}, Reason: {reason})")
            modified_files.append(file_path)

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

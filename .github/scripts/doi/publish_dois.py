import subprocess
import json
import os
import re
import sys

# Add the current script's directory to sys.path to allow importing sibling modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datacite import DataCiteClient

PORTAL_UI_BASE_URL = os.getenv("PORTAL_UI_BASE_URL", "https://opensciencedata.esa.int")

def get_modified_files_in_last_commit():
    """Returns a list of files modified in the last commit, handling merge commits correctly."""
    try:
        # Check if it's a merge commit
        subprocess.check_output(["git", "rev-parse", "--verify", "HEAD^2"], stderr=subprocess.DEVNULL)
        # For a merge commit, this shows changes relative to the first parent (main)
        output = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD^1", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        return output.splitlines()
    except Exception:
        # Fallback for non-merge commits or shallow clones
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
        return None, None
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            properties = data.get("properties", data)
            doi = properties.get("sci:doi") or data.get("sci:doi")
            return doi, data
    except Exception:
        return None, None

def get_file_diff_in_last_commit(file_path):
    """Returns true if the sci:doi field was changed in the last commit."""
    try:
        diff = subprocess.check_output(
            ["git", "diff", "HEAD^", "HEAD", "-U0", "--", file_path],
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        return '"sci:doi"' in diff
    except Exception:
        return True # Fallback to true if we can't check diff

def get_next_version(stac_id):
    """Calculates the next version number based on existing git tags."""
    try:
        # Find the latest version tag for this item
        tags = subprocess.check_output(
            ["git", "tag", "-l", f"{stac_id}-v*"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").splitlines()
        
        versions = []
        for t in tags:
            try:
                v = int(t.split("-v")[-1])
                versions.append(v)
            except ValueError:
                continue
        
        return max(versions) + 1 if versions else 1
    except Exception as e:
        print(f"Error calculating next version for {stac_id}: {e}")
        return 1

def create_and_push_tag(stac_id, version, doi):
    """Creates a git tag for the version and pushes it to origin."""
    try:
        tag_name = f"{stac_id}-v{version}"
        
        print(f"Creating tag {tag_name} for DOI {doi}")
        subprocess.check_call(["git", "tag", "-a", tag_name, "-m", f"Published DOI: {doi}"])
        subprocess.check_call(["git", "push", "origin", tag_name])
        return tag_name
    except Exception as e:
        print(f"Failed to create/push tag for {stac_id}: {e}")
        return None

def main():
    try:
        client = DataCiteClient()
    except ValueError as e:
        print(f"Error: {e}")
        return

    files = get_modified_files_in_last_commit()
    print(f"Found {len(files)} modified files in this commit.")
    published_count = 0

    for file_path in files:
        is_product_file = file_path.endswith("collection.json") and "products/" in file_path
        is_workflow_file = file_path.endswith("record.json") and "workflows/" in file_path
        
        if is_product_file or is_workflow_file:
            doi, stac_item = extract_doi_from_file(file_path)
            if not doi:
                print(f"Skipping {file_path}: No DOI found or invalid JSON.")
                continue

            # Check if it's a draft on DataCite
            try:
                state = client.get_doi_state(doi)
                if state == "draft":
                    print(f"Publishing DOI {doi} for {file_path} (State: {state})")
                    # Construct target URL with version suffix
                    stac_id = stac_item.get("id")
                    properties = stac_item.get("properties", stac_item)
                    raw_type = properties.get("osc:type", stac_item.get("osc:type", properties.get("type", "product")))
                    stac_type = "workflow" if raw_type == "workflow" else "product"
                    suffix = "/collection" if stac_type == "product" else "/record"
                    
                    next_version = get_next_version(stac_id)
                    target_url = f"{PORTAL_UI_BASE_URL}/{stac_type}s/{stac_id}{suffix}_v{next_version}"
                    
                    client.publish_doi(doi, target_url)
                    print(f"Successfully published {doi} with target URL: {target_url}")
                    
                    # Create and push git tag
                    create_and_push_tag(stac_id, next_version, doi)
                    
                    published_count += 1
                else:
                    print(f"Skipping {file_path}: DOI {doi} is already in state '{state}'.")
            except Exception as e:
                print(f"Failed to check or publish DOI {doi} for {file_path}: {e}")

    print(f"Finished. Published {published_count} DOIs.")

if __name__ == "__main__":
    main()

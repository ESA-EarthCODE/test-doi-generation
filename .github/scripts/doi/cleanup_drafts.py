import os
import json
import subprocess
import sys

# Add the current script's directory to sys.path to allow importing sibling modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datacite import DataCiteClient

def get_doi_from_file_at_commit(file_path: str, commit: str) -> str | None:
    """Extracts sci:doi from a file at a specific commit."""
    try:
        content = subprocess.check_output(
            ["git", "show", f"{commit}:{file_path}"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        data = json.loads(content)
        properties = data.get("properties", data)
        return properties.get("sci:doi") or data.get("sci:doi")
    except Exception:
        return None

def main():
    try:
        client = DataCiteClient()
    except ValueError as e:
        print(f"Error: {e}")
        return

    base_ref = os.environ.get("BASE_REF")
    head_ref = os.environ.get("HEAD_REF")

    if not base_ref or not head_ref:
        print("BASE_REF or HEAD_REF environment variables are missing.")
        return

    print(f"Comparing PR branch ({head_ref}) against base branch ({base_ref})")

    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        
        changed_files = [f for f in diff_output.splitlines() if f.endswith("collection.json") or f.endswith("record.json")]
    except Exception as e:
        print(f"Failed to get git diff: {e}")
        return

    if not changed_files:
        print("No STAC Collections or OGC Records were modified in this PR. Nothing to clean up.")
        return

    deleted_count = 0
    for file_path in changed_files:
        head_doi = get_doi_from_file_at_commit(file_path, head_ref)
        base_doi = get_doi_from_file_at_commit(file_path, base_ref)

        # Only consider deleting if the PR has a DOI, and it's different from the base branch's DOI
        if head_doi and head_doi != base_doi:
            state = client.get_doi_state(head_doi)
            
            # We ONLY delete if it's a draft. (DataCite API also strictly enforces this)
            if state == "draft":
                print(f"Deleting dangling draft DOI {head_doi} for {file_path}")
                try:
                    client.delete_doi(head_doi)
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete DOI {head_doi}: {e}")
            else:
                print(f"DOI {head_doi} is in state '{state}', skipping deletion.")
        else:
            print(f"No new DOI detected for {file_path} in this PR.")

    print(f"Cleanup complete. Deleted {deleted_count} draft DOIs.")

if __name__ == "__main__":
    main()

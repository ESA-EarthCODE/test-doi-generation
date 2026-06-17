import os
import json
import glob
import subprocess
import shutil
from typing import List, Dict, Any, Optional

def get_git_history(file_path: str) -> List[str]:
    """Returns a list of commit hashes that modified the file, from newest to oldest."""
    try:
        output = subprocess.check_output(
            ["git", "log", "--format=%H", "--", file_path],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        return output.splitlines() if output else []
    except Exception:
        return []

def get_file_at_commit(file_path: str, commit_hash: str) -> Optional[Dict[str, Any]]:
    """Returns the JSON content of a file at a specific commit."""
    try:
        content = subprocess.check_output(
            ["git", "show", f"{commit_hash}:{file_path}"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8")
        return json.loads(content)
    except Exception:
        return None

def get_doi(data: Dict[str, Any]) -> Optional[str]:
    """Extracts sci:doi from STAC Collection or OGC Record."""
    properties = data.get("properties", data)
    return properties.get("sci:doi") or data.get("sci:doi")

def build_versioned_files(file_path: str, dist_dir: str):
    """Extracts historical versions based on DOI changes and writes them to dist."""
    history = get_git_history(file_path)
    if not history:
        return

    # Find unique DOIs and the latest commit for each
    versions_data = []
    seen_dois = set()
    
    # Process history from newest to oldest to find the latest state for each DOI
    for commit in history:
        data = get_file_at_commit(file_path, commit)
        if not data:
            continue
        
        doi = get_doi(data)
        if doi and doi not in seen_dois:
            versions_data.append(data)
            seen_dois.add(doi)

    # Reverse to have oldest first (v1, v2, ...)
    versions_data.reverse()
    
    num_versions = len(versions_data)
    target_subdir = os.path.dirname(os.path.join(dist_dir, file_path))
    os.makedirs(target_subdir, exist_ok=True)
    filename = os.path.basename(file_path) # e.g., collection.json
    base_name, ext = os.path.splitext(filename)

    for i, data in enumerate(versions_data):
        v_num = i + 1
        v_filename = f"{base_name}_v{v_num}{ext}"
        
        # Inject links
        links = data.get("links", [])
        
        # Latest version link
        links.append({
            "rel": "latest-version",
            "href": filename,
            "type": "application/json",
            "title": "Latest version"
        })
        
        # Predecessor
        if v_num > 1:
            links.append({
                "rel": "predecessor-version",
                "href": f"{base_name}_v{v_num-1}{ext}",
                "type": "application/json",
                "title": "Predecessor"
            })
            
        # Successor
        if v_num < num_versions:
            links.append({
                "rel": "successor-version",
                "href": f"{base_name}_v{v_num+1}{ext}",
                "type": "application/json",
                "title": "Successor"
            })
        
        data["links"] = links
        
        with open(os.path.join(target_subdir, v_filename), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    # Copy current version as the main file
    latest_data = get_file_at_commit(file_path, "HEAD")
    if latest_data:
        # Inject navigation links into the latest version too
        links = latest_data.get("links", [])
        links.append({
            "rel": "latest-version",
            "href": filename,
            "type": "application/json",
            "title": "Latest version"
        })
        if num_versions > 0:
             links.append({
                "rel": "predecessor-version",
                "href": f"{base_name}_v{num_versions}{ext}",
                "type": "application/json",
                "title": "Predecessor"
            })
        latest_data["links"] = links
        
        with open(os.path.join(target_subdir, filename), 'w', encoding='utf-8') as f:
            json.dump(latest_data, f, indent=2)

def main():
    dist_dir = "dist"
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir)

    # Copy catalog.json
    if os.path.exists("catalog.json"):
        shutil.copy("catalog.json", os.path.join(dist_dir, "catalog.json"))

    # Process products and workflows
    files = glob.glob("products/**/collection.json", recursive=True) + \
            glob.glob("workflows/**/record.json", recursive=True)

    for file_path in files:
        print(f"Processing versions for {file_path}...")
        build_versioned_files(file_path, dist_dir)

    print(f"Build complete. Files in {dist_dir}/")

if __name__ == "__main__":
    main()

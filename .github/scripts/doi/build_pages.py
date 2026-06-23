import os
import json
import glob
import subprocess
import shutil
from typing import List, Dict, Any, Optional, Tuple

def get_tags_for_item(stac_id: str) -> List[Tuple[int, str, str]]:
    """Returns a list of (version, tag_name, commit_sha) for an item, sorted by version."""
    try:
        output = subprocess.check_output(
            ["git", "tag", "-l", f"{stac_id}-v*"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").splitlines()
        
        tag_list = []
        for t in output:
            try:
                v = int(t.split("-v")[-1])
                # Get commit SHA of the tag
                commit = subprocess.check_output(
                    ["git", "rev-list", "-n", "1", t],
                    stderr=subprocess.DEVNULL
                ).decode("utf-8").strip()
                tag_list.append((v, t, commit))
            except (ValueError, subprocess.CalledProcessError):
                continue
        
        return sorted(tag_list)
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

def is_local_path(href: str) -> bool:
    """Checks if a href is a local relative path (not a URL or absolute path)."""
    if not href:
        return False
    # Check for common protocols
    if any(href.startswith(p) for p in ["http://", "https://", "s3://", "ftp://"]):
        return False
    # If it starts with / it's absolute to the system, which we don't want to version
    if href.startswith("/"):
        return False
    return True

def build_versioned_files(file_path: str, dist_dir: str):
    """Extracts historical versions based on Git tags and writes them to dist."""
    # Load current file to get ID
    with open(file_path, 'r', encoding='utf-8') as f:
        current_data = json.load(f)
    
    properties = current_data.get("properties", current_data)
    stac_id = properties.get("id", current_data.get("id"))
    if not stac_id:
        return

    tags = get_tags_for_item(stac_id)
    if not tags:
        print(f"No tags found for {stac_id}, skipping history.")
        # We still want to copy the latest version though
        copy_latest(file_path, dist_dir, current_data, 0)
        return

    num_versions = len(tags)
    target_subdir = os.path.dirname(os.path.join(dist_dir, file_path))
    os.makedirs(target_subdir, exist_ok=True)
    filename = os.path.basename(file_path) # e.g., collection.json
    base_name, ext = os.path.splitext(filename)

    for i, (v_num, tag_name, commit_sha) in enumerate(tags):
        data = get_file_at_commit(file_path, commit_sha)
        if not data:
            continue
        
        # Version and link STAC Items if they exist
        data = version_items(data, file_path, commit_sha, v_num, target_subdir)
        
        v_filename = f"{base_name}_v{v_num}{ext}"
        
        # Inject navigation links
        links = data.get("links", [])
        links.append({"rel": "latest-version", "href": filename, "type": "application/json", "title": "Latest version"})
        if v_num > 1:
            links.append({"rel": "predecessor-version", "href": f"{base_name}_v{v_num-1}{ext}", "type": "application/json", "title": "Predecessor"})
        if v_num < num_versions:
            links.append({"rel": "successor-version", "href": f"{base_name}_v{v_num+1}{ext}", "type": "application/json", "title": "Successor"})
        
        data["links"] = links
        
        with open(os.path.join(target_subdir, v_filename), 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    # Copy latest
    copy_latest(file_path, dist_dir, current_data, num_versions)

def version_items(collection_data: Dict[str, Any], collection_path: str, commit_sha: str, v_num: str, target_subdir: str) -> Dict[str, Any]:
    """Finds 'item' links, versions the items at the commit_sha, and updates links."""
    links = collection_data.get("links", [])
    new_links = []
    
    collection_dir = os.path.dirname(collection_path)
    
    for link in links:
        if link.get("rel") == "item":
            item_href = link.get("href")
            
            # ONLY version items that are local relative paths
            if is_local_path(item_href):
                # Resolve relative path
                item_path = os.path.normpath(os.path.join(collection_dir, item_href))
                
                item_data = get_file_at_commit(item_path, commit_sha)
                if item_data:
                    # Save versioned item
                    item_basename = os.path.basename(item_path)
                    item_name, item_ext = os.path.splitext(item_basename)
                    v_item_name = f"{item_name}_v{v_num}{item_ext}"
                    
                    # Inject navigation into item too
                    item_links = item_data.get("links", [])
                    item_links.append({"rel": "latest-version", "href": item_basename, "type": "application/json", "title": "Latest version"})
                    item_data["links"] = item_links

                    with open(os.path.join(target_subdir, v_item_name), 'w', encoding='utf-8') as f:
                        json.dump(item_data, f, indent=2)
                    
                    # Update collection link to point to versioned item
                    link["href"] = v_item_name
        
        new_links.append(link)
    
    collection_data["links"] = new_links
    return collection_data

def copy_latest(file_path: str, dist_dir: str, data: Dict[str, Any], num_versions: int):
    """Copies the latest version of the collection and its items to dist."""
    target_subdir = os.path.dirname(os.path.join(dist_dir, file_path))
    os.makedirs(target_subdir, exist_ok=True)
    filename = os.path.basename(file_path)
    base_name, ext = os.path.splitext(filename)

    # Process items for the latest version too
    links = data.get("links", [])
    collection_dir = os.path.dirname(file_path)
    for link in links:
        if link.get("rel") == "item":
            item_href = link.get("href")
            if is_local_path(item_href):
                item_path = os.path.normpath(os.path.join(collection_dir, item_href))
                if os.path.exists(item_path):
                    shutil.copy(item_path, os.path.join(target_subdir, os.path.basename(item_path)))

    # Inject navigation links into the latest version
    links.append({"rel": "latest-version", "href": filename, "type": "application/json", "title": "Latest version"})
    if num_versions > 0:
         links.append({"rel": "predecessor-version", "href": f"{base_name}_v{num_versions}{ext}", "type": "application/json", "title": "Predecessor"})
    data["links"] = links
    
    with open(os.path.join(target_subdir, filename), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def main():
    dist_dir = "dist"
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir)

    if os.path.exists("catalog.json"):
        shutil.copy("catalog.json", os.path.join(dist_dir, "catalog.json"))

    files = glob.glob("products/**/collection.json", recursive=True) + \
            glob.glob("workflows/**/record.json", recursive=True)

    for file_path in files:
        print(f"Processing versioned tags for {file_path}...")
        build_versioned_files(file_path, dist_dir)

    print(f"Build complete. Files in {dist_dir}/")

if __name__ == "__main__":
    main()

import json
import subprocess
import os
from typing import Dict, Any, Optional, Tuple

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

def get_last_doi_change_commit(file_path: str) -> Optional[str]:
    """Finds the last commit hash where 'sci:doi' was modified in the file."""
    try:
        # -G looks for differences that have added or removed a match for the regex
        # We look for the literal "sci:doi"
        output = subprocess.check_output(
            ["git", "log", "-G", '"sci:doi"', "--format=%H", "-n", "1", "--", file_path],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        return output if output else None
    except Exception:
        return None

def is_significant_change(current: Dict[str, Any], historical: Dict[str, Any]) -> bool:
    """Checks if 'extent' or 'links' have significantly changed."""
    # Handle OGC Record structure where extent is in properties
    curr_props = current.get("properties", current)
    hist_props = historical.get("properties", historical)

    # Check Extent
    if curr_props.get("extent") != hist_props.get("extent"):
        return True
    
    # Check Links (Links are typically top-level in both)
    if current.get("links") != historical.get("links"):
        return True
        
    return False

def check_doi_need(file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if a file needs a new DOI.
    Returns (needs_doi, reason).
    """
    if not os.path.exists(file_path):
        return False, None

    with open(file_path, 'r') as f:
        try:
            current_data = json.load(f)
        except json.JSONDecodeError:
            return False, "Invalid JSON"

    # Support nested properties for OGC Records
    properties = current_data.get("properties", current_data)

    if properties.get("osc:skip_doi") is True or current_data.get("osc:skip_doi") is True:
        return False, "Skipped via osc:skip_doi"

    doi = properties.get("sci:doi") or current_data.get("sci:doi")
    if not doi:
        return True, "Missing sci:doi"

    # If DOI exists, check for significant changes since it was last set
    last_commit = get_last_doi_change_commit(file_path)
    if not last_commit:
        # If we can't find a commit that modified sci:doi (maybe it was added in the very first commit?)
        # we'll assume it needs a check against the first commit of the file.
        last_commit = subprocess.check_output(
            ["git", "log", "--reverse", "--format=%H", "--", file_path]
        ).decode("utf-8").splitlines()[0]

    historical_data = get_file_at_commit(file_path, last_commit)
    if not historical_data:
        return False, "Could not retrieve historical data"

    if is_significant_change(current_data, historical_data):
        return True, f"Significant changes detected since {last_commit}"

    return False, None

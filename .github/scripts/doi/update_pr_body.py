import os
import json
import urllib.request
import urllib.error
import re

def main():
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    if event_name != "pull_request_target":
        return
    
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    changed_files_env = os.environ.get("CHANGED_FILES", "")
    changed_files = [f for f in changed_files_env.strip().split() if f]
    
    if not changed_files:
        return

    if not event_path or not os.path.exists(event_path):
        print("GITHUB_EVENT_PATH not found.")
        return

    with open(event_path, 'r') as f:
        event_data = json.load(f)
    
    pr = event_data.get("pull_request")
    if not pr:
        return
    
    pr_body = pr.get("body") or ""
    pr_url = pr.get("url")
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("No GITHUB_TOKEN available, skipping PR body update.")
        return

    # Parse existing checkboxes to preserve state
    existing_states = {}
    for match in re.finditer(r"-\s*\[([ xX])\]\s*Request new DOI version for `([^`]+)`", pr_body):
        state = match.group(1).lower() == 'x'
        filepath = match.group(2)
        existing_states[filepath] = state
    
    # Generate new checklist
    checklist_lines = [
        "<!-- DOI_CHECKLIST_START -->",
        "### 🏷️ DOI Versioning",
        "Select the files you want to generate a new DOI version for. (Otherwise, only the metadata of the Canonical DOI will be updated).",
        ""
    ]
    for f in changed_files:
        mark = "x" if existing_states.get(f) else " "
        checklist_lines.append(f"- [{mark}] Request new DOI version for `{f}`")
    checklist_lines.append("<!-- DOI_CHECKLIST_END -->")
    new_checklist_str = "\n".join(checklist_lines)

    # Replace or append
    if "<!-- DOI_CHECKLIST_START -->" in pr_body and "<!-- DOI_CHECKLIST_END -->" in pr_body:
        new_body = re.sub(
            r"<!-- DOI_CHECKLIST_START -->.*<!-- DOI_CHECKLIST_END -->",
            new_checklist_str,
            pr_body,
            flags=re.DOTALL
        )
    else:
        new_body = pr_body + "\n\n" + new_checklist_str
    
    if new_body.strip() == pr_body.strip():
        print("PR body is already up to date.")
        return
    
    # Update PR via GitHub API
    req = urllib.request.Request(pr_url, method="PATCH", data=json.dumps({"body": new_body}).encode("utf-8"), headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req) as response:
            print("Successfully updated PR body with dynamic DOI checklist.")
    except urllib.error.HTTPError as e:
        print(f"Failed to update PR body: {e.read().decode('utf-8')}")

if __name__ == "__main__":
    main()

# DOI Assignment System

This directory contains the logic and automation for assigning [DataCite](https://datacite.org/) DOIs to STAC Collections (Products and Workflows) within the Open Science Catalog.

## Logic & Architecture

The system follows a **Research -> Strategy -> Execution** lifecycle, implemented via an automated Pull Request workflow and a versioned deployment process.

### 1. Detection & Automation Phase
The system automatically identifies the need for a DOI or an update:
- **New Item:** A STAC Collection (`products/**/collection.json`) or OGC Record (`workflows/**/record.json`) lacks the `sci:doi` property.
- **Significant Change:** An item has an existing `sci:doi`, but its `extent` or `links` have been modified since the DOI was last assigned.
- **Workflow Triggers:**
    - **Pull Requests:** When a PR is opened or updated, the system automatically audits the changed files. If a DOI is needed, it generates/updates a draft and **auto-commits** the change back to the PR branch (handling forks via `pull_request_target`).
    - **Manual Audit:** Triggered via `workflow_dispatch`, it performs a global audit and creates a **new Pull Request** for any missing DOIs, providing a safety buffer for maintainers.

### 2. Intelligent DOI Management
To maintain a clean DataCite registry, the system distinguishes between drafts and published DOIs:
- **Draft Updates:** If a file already has a DOI that is still in a `draft` state (e.g., during iterative PR reviews), the system **updates the existing DOI metadata** instead of creating a new one.
- **Versioning:** If the existing DOI is already `findable` (published) and a significant change is detected, the system creates a **new Draft DOI** to represent the new version.
- **Dangling Draft Cleanup:** If a Pull Request is closed *without* being merged, a dedicated workflow (`doi-cleanup.yml`) compares the PR's DOIs against the base branch. It safely deletes any unmerged, newly created Draft DOIs via the DataCite API, preventing registry clutter.

### 3. Publication Phase
When a DOI assignment PR is merged into `main`:
1. The system identifies the newly added/modified DOIs.
2. It calls the DataCite API to transition these DOIs from `Draft` to `Findable` (Published).
3. It sets the DOI's target URL to the corresponding item page in the Portal UI.

### 4. Versioned GitHub Pages Deployment
On every push to `main`, the system builds a versioned static site:
- **History Extraction:** The system traverses Git history to extract every unique version of an item based on its DOI history.
- **File Structure:** Versions are stored as `collection_v1.json`, `collection_v2.json`, etc., with `collection.json` always serving the latest state.
- **Navigation Links:** Each JSON file is injected with STAC-compliant links for navigation:
    - `latest-version`: Points to the main `collection.json`.
    - `predecessor-version`: Points to the previous version.
    - `successor-version`: Points to the next version.

## Components (Location: `.github/scripts/doi/`)

- `datacite.py`: Low-level wrapper for DataCite REST API. Supports state detection, updates, and deletions.
- `check_changes.py`: Git-based change detection logic.
- `generate_drafts.py`: Main script for the detection phase; updates local files and manages draft DOIs.
- `publish_dois.py`: Main script for the publication phase; finalizes DOIs on DataCite.
- `build_pages.py`: Build script for the versioned GitHub Pages deployment.
- `cleanup_drafts.py`: Target script for deleting abandoned drafts when a PR is closed.

## Configuration (GitHub Secrets)
...
The following secrets must be configured in the GitHub repository:

| Secret | Description |
| :--- | :--- |
| `DATACITE_USER` | DataCite Repository Account ID |
| `DATACITE_PASSWORD` | DataCite Repository Password |
| `DATACITE_PREFIX` | Assigned DOI Prefix |
| `DATACITE_API_URL` | DataCite API Base URL |
| `BOT_PAT` | (Optional) Personal Access Token for auto-committing to forks |

## Metadata Overrides & Manual Control

- **Skip DOI:** To prevent an item from receiving a DOI, add `"osc:skip_doi": true` to its `collection.json`.
- **Manual Reverts (The "Veto"):** If the automated PR proposes a DOI update that is not desired (e.g., a false positive or an insignificant change):
    1.  Manually edit the PR branch.
    2.  Revert the `sci:doi` field in the affected `collection.json` to its previous value (or remove it).
    3.  The publication workflow (`publish_dois.py`) is designed to be surgical: it performs a `git diff` and **only** publishes DOIs that were actually modified in the merge commit.
- **Persistent State:** Once a PR is merged with a reverted or existing DOI, the audit logic recognizes that the file matches the state of the "last DOI change" and will not flag it again until a new significant change occurs.

## File Formatting & Integrity

The system is designed to be "invisible" in your git history:
- **Indentation:** The scripts automatically detect and preserve the existing indentation (2 spaces, 4 spaces, or tabs) of each `collection.json`.
- **Encoding:** Files are handled as UTF-8. Special characters (e.g., `°`, `²`) are preserved as literals and are **not** escaped (e.g., no `\u00b0`).
- **Trailing Newlines:** Standard POSIX trailing newlines are enforced to prevent linting errors and git diff noise.

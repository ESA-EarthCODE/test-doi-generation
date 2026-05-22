# DOI Assignment System

This directory contains the logic and automation for assigning [DataCite](https://datacite.org/) DOIs to STAC Collections (Products and Workflows) within the Open Science Catalog.

## Logic & Architecture

The system follows a **Research -> Strategy -> Execution** lifecycle, implemented via a two-step "Draft-then-Publish" workflow to ensure cost-efficiency and human oversight.

### 1. Detection Phase (The "Audit")
The system identifies the need for a DOI if:
- **New Item:** A STAC Collection in `products/` or `workflows/` lacks the `sci:doi` property.
- **Significant Change:** An item has an existing `sci:doi`, but its `extent` or `links` have been modified since the DOI was last assigned.
    - *Logic:* The system uses `git log -G '"sci:doi"'` to find the last commit that modified the DOI, retrieves the file state at that commit, and performs a deep comparison of the `extent` and `links` objects.

### 2. Draft Creation
When a need is detected, the system:
1. Maps STAC metadata to DataCite XML/JSON (Titles, Creators from `providers`, Publication Year, etc.).
2. Calls the DataCite API to create a **Draft DOI**. Drafts are free and not yet discoverable.
3. Updates the local `collection.json` with the new `sci:doi` and adds the `https://stac-extensions.github.io/scientific/v1.0.0/schema.json` extension.
4. Opens a Pull Request with a summary of these changes.

### 3. Publication Phase
When the DOI assignment PR is merged into `main`:
1. The system identifies the newly added DOIs in the merge commit.
2. It calls the DataCite API to transition these DOIs from `Draft` to `Findable` (Published).
3. It sets the DOI's target URL to the corresponding item page in the Portal UI.

## Components

- `datacite.py`: Low-level wrapper for DataCite REST API. Uses `urllib` to remain dependency-free.
- `check_changes.py`: Git-based change detection logic.
- `generate_drafts.py`: Main script for the detection phase; updates local files and generates draft DOIs.
- `publish_dois.py`: Main script for the publication phase; finalizes DOIs on DataCite.

## Configuration (GitHub Secrets)

The following secrets must be configured in the GitHub repository for the workflows to function:

| Secret | Description | Default / Example |
| :--- | :--- | :--- |
| `DATACITE_USER` | DataCite Repository Account ID | `MYORG.REPO` |
| `DATACITE_PASSWORD` | DataCite Repository Password | `********` |
| `DATACITE_PREFIX` | Assigned DOI Prefix | `10.xxxx` |
| `DATACITE_API_URL` | DataCite API Base URL | `https://api.test.datacite.org` |

## Metadata Overrides

- **Skip DOI:** To prevent an item from receiving a DOI, add `"osc:skip_doi": true` to its `collection.json`.
- **Manual DOI:** If a scientist provides a DOI manually via `sci:doi`, the system will validate its existence and only trigger a new one if significant changes occur subsequently.

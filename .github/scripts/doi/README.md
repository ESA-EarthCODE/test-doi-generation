# DOI Assignment System

This directory contains the logic and automation for assigning [DataCite](https://datacite.org/) DOIs to STAC Collections (Products and Workflows) within the Open Science Catalog.

## Logic & Architecture

The system follows a **Research -> Strategy -> Execution** lifecycle, implemented via a two-step "Draft-then-Publish" workflow to ensure cost-efficiency and human oversight.

### 1. Detection Phase (The "Audit")
The system identifies the need for a DOI if:
- **New Item:** A STAC Collection (`products/**/collection.json`) or OGC Record (`workflows/**/record.json`) lacks the `sci:doi` property.
- **Significant Change:** An item has an existing `sci:doi`, but its `extent` or `links` have been modified since the DOI was last assigned.
    - *Logic:* The system uses `git log -G '"sci:doi"'` to find the last commit that modified the DOI, retrieves the file state at that commit, and performs a deep comparison of the `extent` and `links` objects (accounting for nested properties in Records).

### 2. Draft Creation
When a need is detected, the system performs a context-aware update based on the file type:

#### Metadata Mapping & Extraction
The system intelligently switches extraction logic based on whether it is a Product (STAC) or a Workflow (OGC Record):
- **Products (STAC):** Metadata is extracted from the top-level JSON fields.
- **Workflows (OGC Record):** Metadata (title, description, keywords, dates, etc.) is primarily extracted from the nested `properties` object.
- **Common Mapping:**
    - **Titles:** From STAC `title`.
    - **Creators:** From `providers` with the `producer` role.
    - **Publisher:** From `providers` with the `host` role (defaults to "ESA Earthcode").
    - **Contributors:** From `providers` with roles like `licensor`, `processor`, or `contributor`.
    - **Subjects:** All entries from the `keywords` array.
    - **Dates:** `created` (DateType: Created) and `updated` (DateType: Updated) timestamps.
    - **Geolocations:** Converts `extent.spatial.bbox` into DataCite `geoLocationBox` objects.
    - **Related Identifiers:** Maps `links` (`cite-as`, `via`, `derived_from`, `git`) to DataCite `relatedIdentifiers`.
    - **Language:** Defaults to `en`.

#### Surgical File Updates
To maintain formatting and standard compliance, the `sci:doi` and extension registration are placed differently:
- **Products (`collection.json`):** 
    - `sci:doi` is placed at the top level.
    - Extension URL is added to the `stac_extensions` array.
- **Workflows (`record.json`):** 
    - `sci:doi` is placed inside the `properties` block.
    - Extension URL is added to the `conformsTo` array.
- **Formatting Preservation:** All updates use string-insertion logic to preserve mixed indentation (2-space vs 4-space), UTF-8 characters (no escaping), and existing file structure.

...

3. Updates the local `collection.json` with the new `sci:doi` and adds the `https://stac-extensions.github.io/scientific/v1.0.0/schema.json` extension.
4. Opens a Pull Request with a summary of these changes.

### 3. Publication Phase
When the DOI assignment PR is merged into `main`:
1. The system identifies the newly added DOIs in the merge commit.
2. It calls the DataCite API to transition these DOIs from `Draft` to `Findable` (Published).
3. It sets the DOI's target URL to the corresponding item page in the Portal UI.

## Components (Location: `.github/scripts/doi/`)

- `datacite.py`: Low-level wrapper for DataCite REST API. Uses `urllib` to remain dependency-free.
- `check_changes.py`: Git-based change detection logic.
- `generate_drafts.py`: Main script for the detection phase; updates local files and generates draft DOIs.
- `publish_dois.py`: Main script for the publication phase; finalizes DOIs on DataCite.

## Configuration (GitHub Secrets)
...
The following secrets must be configured in the GitHub repository for the workflows to function:

| Secret | Description | Default / Example |
| :--- | :--- | :--- |
| `DATACITE_USER` | DataCite Repository Account ID | `MYORG.REPO` |
| `DATACITE_PASSWORD` | DataCite Repository Password | `********` |
| `DATACITE_PREFIX` | Assigned DOI Prefix | `10.xxxx` |
| `DATACITE_API_URL` | DataCite API Base URL | `https://api.test.datacite.org` |

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

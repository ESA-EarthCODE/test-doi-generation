# DOI Assignment System

This directory contains the logic and automation for assigning [DataCite](https://datacite.org/) DOIs to STAC Collections (Products and Workflows) within the Open Science Catalog.

## Logic & Architecture

The system follows a **Research -> Strategy -> Execution** lifecycle, implemented via an automated Pull Request workflow and a versioned deployment process.
### 1. Detection & Automation Phase
The system automatically identifies the need for a DOI or an update by comparing the current file state against its **official historical baseline**.

- **New Item:** A STAC Collection (`products/**/collection.json`) or OGC Record (`workflows/**/record.json`) lacks the `sci:doi` property.
- **Historical Baseline Detection:** For items with existing DOIs, the system searches for a baseline in this priority order:
    1. **Version Tags:** The commit of the highest version tag (`<stac_type>-<id>-v*`). By prefixing with `product-` or `workflow-`, the system prevents namespace collisions between identically named items.
    2. **String Match:** The last commit that modified the `"sci:doi"` string (fallback for untagged legacy items).
    3. **Permissive Baseline:** If neither are found, the current state (`HEAD`) is assumed to be the validated baseline ("v1").
- **Significant Change:** A new DOI draft is triggered if any of the following fields have been modified relative to the detected baseline: `title`, `description`, `keywords`, `providers`, `extent`, or `links`.
- **Workflow Triggers:**
...
    - **Pull Requests:** When a PR is opened or updated, the system automatically audits the changed files. If a DOI is needed, it generates/updates a draft and **auto-commits** the change back to the PR branch (handling forks via `pull_request_target`).
    - **Scheduled/Manual Audit:** Triggered daily via a `schedule` or manually via `workflow_dispatch`, it performs a **full repository audit**. It creates a **new Pull Request** containing all items requiring a new or updated DOI, providing a safety buffer for maintainers.

### 2. Intelligent DOI Management
To maintain a clean DataCite registry, the system distinguishes between drafts and published DOIs:
- **Draft Updates:** If a file already has a DOI that is still in a `draft` state (e.g., during iterative PR reviews), the system **updates the existing DOI metadata** instead of creating a new one.
- **Versioning:** If the existing DOI is already `findable` (published) and a significant change is detected, the system creates a **new Draft DOI** to represent the new version.
- **Foreign DOI Migration:** If an item has an existing `sci:doi` from an external source (not matching the configured `DATACITE_PREFIX`), the system will replace it with a new local DOI. The old foreign DOI is automatically moved to the `sci:publications` array to preserve the reference.
- **Dangling Draft Cleanup:** If a Pull Request is closed *without* being merged, a dedicated workflow (`doi-cleanup.yml`) compares the PR's DOIs against the base branch. It safely deletes any unmerged, newly created Draft DOIs via the DataCite API, preventing registry clutter.

### 3. Publication Phase
When a DOI assignment PR is merged into `main`:
1. The system identifies the newly added/modified DOIs.
2. It calls the DataCite API to transition these DOIs from `Draft` to `Findable` (Published).
3. It sets the DOI's target URL to the corresponding item page in the Portal UI.

### 4. Versioned GitHub Pages Deployment
On every push to `main`, the system builds a versioned static site:
- **Tag-Based History:** The system extracts historical versions strictly based on Git tags (`<stac_type>-<item-id>-v*`).
- **Recursive Item Versioning:** For every Collection version, the system identifies associated local STAC Items (via `rel: "item"` links) and saves snapshots of them at the exact same tagged commit.
- **Link Rewriting:** Versioned Collections are updated to point to their corresponding versioned Items, ensuring a consistent point-in-time snapshot.
- **Navigation Links:** Each JSON file is injected with STAC-compliant links for navigation:
    - `latest-version`: Points to the explicitly versioned file of the latest release (e.g., `collection_v3.json`). This link is omitted if the file is currently the latest version.
    - `predecessor-version`: Points to the previous version (e.g., `collection_v1.json`).
    - `successor-version`: Points to the next version.

## DataCite Metadata Mapping

The system automatically extracts provider information from your STAC/OGC metadata to populate DataCite fields. This logic relies on the STAC Provider `roles` array:

- **Creator (Mandatory, 1+):** Extracted from any provider with the `producer` role. 
  - *Fallback:* If no producer is found, it defaults to `"ESA EarthCODE"` (mapped with `nameType: "Organizational"`).
- **Publisher (Mandatory, exactly 1):** Extracted from the provider with the `host` role. 
  - *Conflict Resolution:* If multiple providers have the `host` role, the **last** one listed in the file is used, as DataCite strictly requires a single publisher.
  - *Fallback:* If no host is found, it defaults to `"ESA EarthCODE"`.
- **Contributor (Optional):** Extracted from providers with `licensor`, `processor`, or `contributor` roles.
  - *Note:* `processor` providers are mapped as `DataCollector`, while `licensor` or `contributor` providers are mapped as `Distributor`.

## Components (Location: `.github/scripts/doi/`)

- `datacite.py`: Low-level wrapper for DataCite REST API. Supports state detection, updates, and deletions.
- `check_changes.py`: Git-based change detection logic.
- `generate_drafts.py`: Main script for the detection phase; updates local files and manages draft DOIs.
- `publish_dois.py`: Main script for the publication phase; finalizes DOIs on DataCite.
- `build_pages.py`: Build script for the versioned GitHub Pages deployment.
- `cleanup_drafts.py`: Target script for deleting abandoned drafts when a PR is closed.

## Configuration (GitHub Secrets & Variables)

The following configurations must be set in the GitHub repository for the workflows to function correctly:

### Secrets
| Secret | Description | Required |
| :--- | :--- | :--- |
| `DATACITE_USER` | DataCite Repository Account ID (e.g., `MYORG.REPO`) | **Yes** |
| `DATACITE_PASSWORD` | DataCite Repository Password | **Yes** |
| `DATACITE_PREFIX` | Assigned DOI Prefix (e.g., `10.xxxx`) | **Yes** |
| `DATACITE_API_URL` | DataCite API Base URL (Defaults to `https://api.test.datacite.org`) | No |
| `BOT_PAT` | Personal Access Token used to auto-commit DOIs back to PRs (handling forks) and to create the Scheduled/Manual Audit PRs so that CI validation workflows are triggered. | No* |

*\*Highly recommended for a smooth contributor experience.*

### Variables
| Variable | Description | Default |
| :--- | :--- | :--- |
| `PORTAL_UI_BASE_URL` | Base URL for the Open Science Catalog UI. Used to construct the DOI target URL. | `https://opensciencedata.esa.int` |

## Metadata Overrides & Manual Control

- **Skip DOI:** To prevent an item from receiving a DOI, add `"osc:skip_doi": true` to its `collection.json` or `record.json`.
- **Manual Reverts (The "Veto"):** If the automated PR proposes a DOI update that is not desired (e.g., a false positive or an insignificant change):
    1.  Manually edit the PR branch and revert the `sci:doi` field to its previous value (or remove it if it was new).
    2.  The publication workflow (`publish_dois.py`) only publishes DOIs that are present and modified in the merge commit. Reverting the field ensures no DOI action is taken.
    3.  **Baseline Note:** Since the historical baseline is driven by **Git Tags** (`<stac_type>-<id>-v*`), a vetoed item will be flagged again by the next audit if the significant changes remain. To stop future audits from flagging the item, you must either revert the significant changes, accept the DOI, or use `osc:skip_doi`.
- **Version Tags as Baselines:** The baseline for change detection only advances when a new version tag is created. This happens automatically when a new DOI is published. If you need to "approve" a metadata state as the new baseline *without* updating the DOI, you would need to manually create and push a new version tag for that item.
- **Persistent State:** For untagged legacy items, the system defaults to a **Permissive Baseline**, treating the current repository state as the initial validated version.

# ClearMLOps — Image Scraping & Dataset Versioning Pipeline (Phase 1)

A modular Python pipeline that:

1. **Scrapes** image data from online sources (`requests` + `BeautifulSoup`, or a
   supplied URL list / built-in samples).
2. **Stores** the images in a clean, timestamped local directory
   (`./raw_data/images_YYYYMMDD_HHMMSS/`).
3. **Versions & uploads** that directory as a [ClearML `Dataset`](https://clear.ml/docs/latest/docs/clearml_data/)
   (`create → add_files → upload → finalize`).

The scraping logic and the ClearML logic are fully decoupled — see
[Project layout](#project-layout).

---

## Project layout

```
ClearMLOps/
├── run_pipeline.py            # CLI entry point / orchestrator
├── requirements.txt
├── urls.sample.txt            # example --url-file input
└── pipeline/
    ├── __init__.py
    ├── config.py              # all tunables + sample URLs (PipelineConfig)
    ├── logging_config.py      # shared logging setup
    ├── scraper.py             # Step 1: extract_image_urls(), scrape_images()
    ├── storage.py             # Step 2: create_run_directory()
    └── clearml_dataset.py     # Step 3: version_and_upload()  (only file importing clearml)
```

| Concern            | Module                       | Knows about ClearML? |
| ------------------ | ---------------------------- | -------------------- |
| Scraping           | `pipeline/scraper.py`        | No                   |
| Local storage      | `pipeline/storage.py`        | No                   |
| Dataset versioning | `pipeline/clearml_dataset.py`| Yes (exclusively)    |
| Orchestration      | `run_pipeline.py`            | Wires the stages     |

---

## 1. Install

```bash
# from the project root (d:\ClearMLOps)
python -m venv .venv
.venv\Scripts\activate        # PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Python 3.10+ is required (the code uses `X | None` type syntax).

---

## 2. Set up ClearML credentials (do this **before** running)

You need access to a ClearML Server — either the free hosted
[app.clear.ml](https://app.clear.ml) or a self-hosted instance.

### Option A — interactive wizard (recommended)

1. Log in to your ClearML web UI.
2. Go to **Settings → Workspace → Create new credentials**.
3. Copy the generated block (it looks like the snippet below).
4. Run:

   ```bash
   clearml-init
   ```

   Paste the credentials block when prompted. This writes a config file to:

   * **Windows:** `C:\Users\<you>\clearml.conf`
   * **Linux/Mac:** `~/clearml.conf`

### Option B — environment variables (good for CI / containers)

No `clearml.conf` needed; set these in your shell before running the pipeline:

```powershell
# PowerShell
$env:CLEARML_WEB_HOST      = "https://app.clear.ml"
$env:CLEARML_API_HOST      = "https://api.clear.ml"
$env:CLEARML_FILES_HOST    = "https://files.clear.ml"
$env:CLEARML_API_ACCESS_KEY = "<your access key>"
$env:CLEARML_API_SECRET_KEY = "<your secret key>"
```

```bash
# bash
export CLEARML_WEB_HOST="https://app.clear.ml"
export CLEARML_API_HOST="https://api.clear.ml"
export CLEARML_FILES_HOST="https://files.clear.ml"
export CLEARML_API_ACCESS_KEY="<your access key>"
export CLEARML_API_SECRET_KEY="<your secret key>"
```

### What a credentials block looks like

```
api {
    web_server: https://app.clear.ml
    api_server: https://api.clear.ml
    files_server: https://files.clear.ml
    credentials {
        access_key: "ABC123..."
        secret_key: "xyz789..."
    }
}
```

### Verify

```bash
python -c "from clearml.backend_api import Session; print('ClearML auth OK:', Session().get_api_server_host())"
```

> **Never commit `clearml.conf` or secret keys.** They are already in `.gitignore`.

---

## 3. Run the pipeline

```bash
# Simplest: uses the built-in sample image URLs from pipeline/config.py
python run_pipeline.py

# Scrape <img> tags from a real page
python run_pipeline.py --page https://en.wikipedia.org/wiki/Cat

# Use your own list of URLs
python run_pipeline.py --url-file urls.sample.txt

# Custom ClearML target
python run_pipeline.py --project "Image_Scraping_Project" --dataset "Raw_Images"

# Push files to your own storage instead of the ClearML file server
python run_pipeline.py --output-uri s3://my-bucket/scraped-images

# Add this run on top of the previous dataset version (delta upload)
python run_pipeline.py --append

# Scrape + store locally only, skip ClearML entirely
python run_pipeline.py --skip-clearml
```

### Expected log output (abridged)

```
2026-09-03 12:00:01 | INFO    | pipeline.storage    | Created run directory: d:\ClearMLOps\raw_data\images_20260903_120001
2026-09-03 12:00:01 | INFO    | pipeline.scraper    | Starting download of 9 image URL(s) -> raw_data\images_20260903_120001
2026-09-03 12:00:03 | WARNING | pipeline.scraper    | Attempt 1/3 failed for https://picsum.photos/this-will-404: 404 Client Error ...
2026-09-03 12:00:07 | INFO    | pipeline.scraper    | Download complete: 8 succeeded, 1 failed
2026-09-03 12:00:07 | INFO    | run_pipeline        | Downloaded 8 image(s) into raw_data\images_20260903_120001
2026-09-03 12:00:07 | INFO    | run_pipeline        | Uploading to ClearML...
2026-09-03 12:00:12 | INFO    | pipeline.clearml_dataset | Dataset version created: ID=6f2a1c9d8e4b4f0aa1b2c3d4e5f60718
2026-09-03 12:00:12 | INFO    | run_pipeline        | ====================================================================
2026-09-03 12:00:12 | INFO    | run_pipeline        | Pipeline finished.
2026-09-03 12:00:12 | INFO    | run_pipeline        |   Dataset version : ID=6f2a1c9d8e4b4f0aa1b2c3d4e5f60718
```

You can then browse the dataset in the ClearML UI under
**Datasets → Image_Scraping_Project → Raw_Images**.

---

## 4. Retrieving the versioned data later

```python
from clearml import Dataset

ds = Dataset.get(dataset_project="Image_Scraping_Project", dataset_name="Raw_Images")
local_copy = ds.get_local_copy()   # cached, read-only path to the exact version
print(local_copy)
```

---

## Design notes / best practices applied

* **Decoupling** — `scraper.py` / `storage.py` never import `clearml`;
  `clearml_dataset.py` never imports `requests`. `run_pipeline.py` is the only
  place the two halves meet.
* **Error handling** — per-image retries with backoff, content-type and size
  validation, and a `ScrapeResult` that records every failure instead of
  aborting the run. The pipeline still versions whatever downloaded
  successfully.
* **Deterministic storage** — one timestamped directory per run; nothing is
  ever overwritten, so each ClearML version maps to an on-disk snapshot.
* **Logging** — single shared formatter via `logging_config.setup_logging()`;
  progress messages match the requested milestones ("Downloaded X images",
  "Uploading to ClearML...", "Dataset version created: ID=...").
* **Configuration** — all knobs live in `PipelineConfig`; CLI flags override
  them without touching code.
* **Idempotent-ish appends** — `--append` chains versions via
  `parent_datasets`, the ClearML-recommended way to grow a dataset.

## Troubleshooting

**`SSLError: certificate verify failed: unable to get local issuer certificate`**
Antivirus (Avast/AVG/Kaspersky) or a corporate proxy is inspecting HTTPS and
re-signing certificates with a local root that Python's `certifi` bundle does
not contain. The pipeline calls `pipeline.tls.configure_tls()` at startup,
which uses the [`truststore`](https://pypi.org/project/truststore/) package to
verify against the OS trust store instead. Make sure it is installed
(`pip install truststore`). Alternatively export the interception root CA to a
PEM and set `PIPELINE_CA_BUNDLE=C:\path\to\corp-root-ca.pem` before running.

## Next phases (not in scope here)

Phase 2+ would add: de-duplication / hashing against previous versions,
image validation (corrupt-file detection with Pillow), a ClearML
`PipelineController` to schedule scrape → clean → label steps, and dataset
statistics reporting.

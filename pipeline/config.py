"""Central configuration for the scraping pipeline.

Everything tunable lives here so the scraper and the ClearML logic stay
free of magic values. Values can be overridden from the command line
(see ``run_pipeline.py``) or by constructing ``PipelineConfig`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Sample data - used when the pipeline is run without an explicit URL source.
# These are small, freely-usable placeholder images.
# --------------------------------------------------------------------------- #
SAMPLE_IMAGE_URLS: list[str] = [
    "https://picsum.photos/id/10/800/600",
    "https://picsum.photos/id/20/800/600",
    "https://picsum.photos/id/30/800/600",
    "https://picsum.photos/id/40/800/600",
    "https://picsum.photos/id/50/800/600",
    "https://picsum.photos/id/60/800/600",
    "https://picsum.photos/id/70/800/600",
    "https://picsum.photos/id/80/800/600",
    # An intentionally broken URL to exercise error handling:
    "https://picsum.photos/this-will-404",
]


@dataclass
class PipelineConfig:
    """Runtime configuration for a single pipeline execution."""

    # --- Scraper -------------------------------------------------------------
    image_urls: list[str] = field(default_factory=lambda: list(SAMPLE_IMAGE_URLS))
    target_page: str | None = None          # if set, scrape <img> tags from here
    request_timeout: float = 15.0           # seconds per HTTP request
    max_retries: int = 3                    # per-image retry attempts
    retry_backoff: float = 1.5              # seconds, multiplied by attempt no.
    user_agent: str = (
        "Mozilla/5.0 (compatible; ClearMLOps-Scraper/0.1; "
        "+https://github.com/allegroai/clearml)"
    )
    allowed_content_types: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
    )
    max_image_bytes: int = 25 * 1024 * 1024  # skip anything larger than 25 MB

    # --- Local storage ----------------------------------------------------- #
    raw_data_root: Path = Path("./raw_data")
    run_dir_prefix: str = "images"          # -> raw_data/images_YYYYMMDD_HHMMSS

    # --- ClearML --------------------------------------------------------- #
    clearml_project: str = "Image_Scraping_Project"
    clearml_dataset_name: str = "Raw_Images"
    clearml_output_uri: str | None = None   # e.g. "s3://bucket/folder" or None
    dataset_tags: tuple[str, ...] = ("scraped", "phase-1", "raw")

    def __post_init__(self) -> None:
        # Normalise to Path so callers may pass plain strings.
        self.raw_data_root = Path(self.raw_data_root)

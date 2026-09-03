"""Local storage management for scraped images.

Responsible only for *where* files live on disk - it knows nothing about
scraping or ClearML. This keeps the filesystem layout in one place and
makes the run directory predictable and easy to track.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)


def create_run_directory(
    root: Path | str = "./raw_data",
    prefix: str = "images",
    timestamp: datetime | None = None,
) -> Path:
    """Create and return a fresh, timestamped directory for one scrape run.

    Layout produced::

        <root>/<prefix>_YYYYMMDD_HHMMSS/

    Parameters
    ----------
    root:
        Parent directory that holds every run (created if missing).
    prefix:
        Human-readable prefix for the run folder.
    timestamp:
        Override the timestamp (useful for tests); defaults to ``now()``.

    Returns
    -------
    Path
        The created run directory (guaranteed to exist and be empty).
    """
    root = Path(root)
    stamp = (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    run_dir = root / f"{prefix}_{stamp}"

    run_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Created run directory: %s", run_dir.resolve())
    return run_dir


def count_files(directory: Path | str) -> int:
    """Return the number of regular files directly inside ``directory``."""
    directory = Path(directory)
    return sum(1 for p in directory.iterdir() if p.is_file())

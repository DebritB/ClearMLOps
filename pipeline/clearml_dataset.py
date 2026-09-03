"""ClearML dataset versioning & upload.

This module is the *only* place that imports ``clearml``. It takes a
directory of files that already exist on disk and turns it into a
finalized, versioned ClearML dataset.

Flow (mirrors the ClearML Dataset lifecycle):

    Dataset.create()  ->  add_files()  ->  upload()  ->  finalize()
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clearml import Dataset

from .config import PipelineConfig
from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class DatasetVersion:
    """Lightweight handle to the dataset version we just created."""

    id: str
    project: str
    name: str
    file_count: int


def version_and_upload(
    files_dir: Path | str,
    config: PipelineConfig | None = None,
    *,
    parent_dataset_id: str | None = None,
) -> DatasetVersion:
    """Create, populate, upload and finalize a ClearML dataset version.

    Parameters
    ----------
    files_dir:
        Local directory whose contents become the dataset payload.
    config:
        Pipeline configuration (project / dataset names, output URI, tags).
    parent_dataset_id:
        Optional ID of a previous version to build on. When supplied, the
        new version is a delta on top of the parent - the standard way to
        add newly-scraped images to an existing dataset.

    Returns
    -------
    DatasetVersion
        Includes the dataset ``id`` you can reference from later pipeline
        stages (preprocessing, training, ...).
    """
    config = config or PipelineConfig()
    files_dir = Path(files_dir)

    if not files_dir.is_dir():
        raise NotADirectoryError(f"{files_dir} is not a directory")

    local_files = [p for p in files_dir.rglob("*") if p.is_file()]
    if not local_files:
        raise ValueError(f"No files found under {files_dir} - nothing to version")

    logger.info(
        "Creating ClearML dataset  project=%r  name=%r  (%d local file(s))",
        config.clearml_project,
        config.clearml_dataset_name,
        len(local_files),
    )

    # 1. create -----------------------------------------------------------
    dataset = Dataset.create(
        dataset_project=config.clearml_project,
        dataset_name=config.clearml_dataset_name,
        parent_datasets=[parent_dataset_id] if parent_dataset_id else None,
        description="Raw images collected by the scraping pipeline (phase 1).",
        output_uri=config.clearml_output_uri,
    )
    if config.dataset_tags:
        dataset.add_tags(list(config.dataset_tags))

    # 2. add_files ------------------------------------------------------- #
    logger.info("Adding files from %s ...", files_dir.resolve())
    dataset.add_files(path=str(files_dir), verbose=False)

    # 3. upload ---------------------------------------------------------- #
    logger.info(
        "Uploading to ClearML%s ...",
        f" ({config.clearml_output_uri})" if config.clearml_output_uri else "",
    )
    dataset.upload(show_progress=True)

    # 4. finalize ------------------------------------------------------ #
    dataset.finalize()
    logger.info("Dataset version created: ID=%s", dataset.id)

    return DatasetVersion(
        id=dataset.id,
        project=config.clearml_project,
        name=config.clearml_dataset_name,
        file_count=len(local_files),
    )


def get_latest_dataset_id(config: PipelineConfig) -> str | None:
    """Return the ID of the most recent finalized version, or ``None``.

    Handy for chaining runs: pass the result as ``parent_dataset_id`` to
    :func:`version_and_upload` so each scrape appends to the same dataset.
    """
    try:
        existing = Dataset.get(
            dataset_project=config.clearml_project,
            dataset_name=config.clearml_dataset_name,
            only_completed=True,
            auto_create=False,
        )
        return existing.id
    except Exception as exc:  # noqa: BLE001 - no prior version is a normal case
        logger.info("No existing dataset version found (%s)", exc)
        return None

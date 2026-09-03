#!/usr/bin/env python3
"""End-to-end runner for Phase 1: scrape images -> store locally -> version in ClearML.

Examples
--------
Run with the built-in sample URLs::

    python run_pipeline.py

Scrape <img> tags from a page::

    python run_pipeline.py --page https://example.com/gallery

Provide your own URL list from a file (one URL per line)::

    python run_pipeline.py --url-file urls.txt \
        --project "Image_Scraping_Project" --dataset "Raw_Images"

Append this run to the previous dataset version instead of starting fresh::

    python run_pipeline.py --append
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.clearml_dataset import get_latest_dataset_id, version_and_upload
from pipeline.config import PipelineConfig
from pipeline.logging_config import get_logger, setup_logging
from pipeline.scraper import extract_image_urls, scrape_images
from pipeline.storage import create_run_directory
from pipeline.tls import configure_tls

logger = get_logger("run_pipeline")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group()
    src.add_argument("--page", help="Web page to scrape <img> tags from.")
    src.add_argument("--url-file", type=Path, help="Text file with one image URL per line.")

    p.add_argument("--project", default=None, help="ClearML dataset project name.")
    p.add_argument("--dataset", default=None, help="ClearML dataset name.")
    p.add_argument("--output-uri", default=None,
                   help="Storage target for uploaded files, e.g. s3://bucket/key. "
                        "Defaults to the ClearML file server.")
    p.add_argument("--raw-root", type=Path, default=None,
                   help="Parent folder for run directories (default ./raw_data).")
    p.add_argument("--append", action="store_true",
                   help="Build on the latest existing dataset version instead of a new one.")
    p.add_argument("--skip-clearml", action="store_true",
                   help="Only scrape + store locally; do not touch ClearML.")
    p.add_argument("--log-level", default="INFO",
                   help="DEBUG / INFO / WARNING / ERROR (default INFO).")
    return p.parse_args(argv)


def _resolve_urls(args: argparse.Namespace, config: PipelineConfig) -> list[str]:
    if args.page:
        return extract_image_urls(args.page, config)
    if args.url_file:
        text = args.url_file.read_text(encoding="utf-8")
        return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    logger.info("No --page / --url-file given; using %d built-in sample URLs.", len(config.image_urls))
    return config.image_urls


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    setup_logging(args.log_level.upper())
    configure_tls()  # trust the OS cert store (AV/proxy HTTPS inspection safe)

    # ------------------------------------------------------------------ #
    # Build config from defaults + CLI overrides
    # ------------------------------------------------------------------ #
    overrides: dict = {}
    if args.project:
        overrides["clearml_project"] = args.project
    if args.dataset:
        overrides["clearml_dataset_name"] = args.dataset
    if args.output_uri:
        overrides["clearml_output_uri"] = args.output_uri
    if args.raw_root:
        overrides["raw_data_root"] = args.raw_root
    config = PipelineConfig(**overrides)

    # ------------------------------------------------------------------ #
    # Stage 1 + 2: scrape and store locally  (ClearML-agnostic)
    # ------------------------------------------------------------------ #
    urls = _resolve_urls(args, config)
    if not urls:
        logger.error("No image URLs to process - aborting.")
        return 2

    run_dir = create_run_directory(config.raw_data_root, config.run_dir_prefix)
    result = scrape_images(urls, run_dir, config)

    if result.success_count == 0:
        logger.error("Every download failed - nothing to version. Aborting.")
        return 1
    logger.info("Downloaded %d image(s) into %s", result.success_count, run_dir)
    if result.failed:
        logger.warning("%d URL(s) failed:", result.failure_count)
        for url, reason in result.failed:
            logger.warning("  - %s (%s)", url, reason)

    # ------------------------------------------------------------------ #
    # Stage 3: ClearML dataset versioning + upload  (scraper-agnostic)
    # ------------------------------------------------------------------ #
    if args.skip_clearml:
        logger.info("--skip-clearml set; stopping after local storage. Files at: %s", run_dir.resolve())
        return 0

    parent_id = get_latest_dataset_id(config) if args.append else None
    if args.append:
        logger.info("Appending to parent dataset: %s", parent_id or "<none found, creating first version>")

    logger.info("Uploading to ClearML...")
    version = version_and_upload(run_dir, config, parent_dataset_id=parent_id)

    logger.info("=" * 68)
    logger.info("Pipeline finished.")
    logger.info("  Local dir       : %s", run_dir.resolve())
    logger.info("  Images versioned: %d", version.file_count)
    logger.info("  ClearML project : %s", version.project)
    logger.info("  ClearML dataset : %s", version.name)
    logger.info("  Dataset version : ID=%s", version.id)
    logger.info("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())

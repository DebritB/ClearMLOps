"""Image scraping + ClearML dataset-versioning pipeline (Phase 1).

Public surface:
    - scraper.scrape_images / scraper.extract_image_urls
    - storage.create_run_directory
    - clearml_dataset.version_and_upload
    - config.PipelineConfig
"""

__version__ = "0.1.0"

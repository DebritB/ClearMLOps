"""Image scraper module.

Two entry points:

* :func:`extract_image_urls` - pull ``<img>`` sources from a web page.
* :func:`scrape_images`      - download a list of image URLs to a folder.

Deliberately has **no** knowledge of ClearML - it just produces files on
disk and reports what succeeded / failed.
"""

from __future__ import annotations

import hashlib
import mimetypes
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import PipelineConfig
from .logging_config import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #
@dataclass
class ScrapeResult:
    """Outcome of a :func:`scrape_images` call."""

    output_dir: Path
    downloaded: list[Path] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (url, reason)

    @property
    def success_count(self) -> int:
        return len(self.downloaded)

    @property
    def failure_count(self) -> int:
        return len(self.failed)


# --------------------------------------------------------------------------- #
# Page parsing (optional BeautifulSoup path)
# --------------------------------------------------------------------------- #
def extract_image_urls(page_url: str, config: PipelineConfig | None = None) -> list[str]:
    """Return absolute image URLs found in ``<img src=...>`` tags on a page.

    Falls back gracefully: any network or parse error is logged and an
    empty list is returned rather than raising.
    """
    config = config or PipelineConfig()
    headers = {"User-Agent": config.user_agent}

    try:
        resp = requests.get(page_url, headers=headers, timeout=config.request_timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Could not fetch page %s: %s", page_url, exc)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    urls: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        absolute = urljoin(page_url, src)
        if urlparse(absolute).scheme in ("http", "https"):
            urls.append(absolute)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique = [u for u in urls if not (u in seen or seen.add(u))]
    logger.info("Extracted %d image URL(s) from %s", len(unique), page_url)
    return unique


# --------------------------------------------------------------------------- #
# Downloading
# --------------------------------------------------------------------------- #
def _filename_for(url: str, content_type: str | None, index: int) -> str:
    """Build a stable, collision-resistant filename for a downloaded image."""
    path_name = Path(urlparse(url).path).name
    stem = Path(path_name).stem or f"image_{index:04d}"

    ext = Path(path_name).suffix
    if not ext and content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or ""
    if not ext:
        ext = ".jpg"

    # Short hash keeps names unique even if two URLs share a basename.
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{index:04d}_{stem}_{digest}{ext}"


def download_image(
    url: str,
    dest_dir: Path,
    index: int,
    config: PipelineConfig,
    session: requests.Session,
) -> Path:
    """Download a single image with retries.

    Returns the written :class:`Path` on success, raises on final failure.
    """
    last_exc: Exception | None = None

    for attempt in range(1, config.max_retries + 1):
        try:
            resp = session.get(
                url,
                timeout=config.request_timeout,
                stream=True,
                headers={"User-Agent": config.user_agent},
            )
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "").lower()
            if content_type and not content_type.startswith("image/"):
                raise ValueError(f"unexpected Content-Type {content_type!r}")
            if (
                content_type
                and config.allowed_content_types
                and not any(content_type.startswith(t) for t in config.allowed_content_types)
            ):
                raise ValueError(f"disallowed Content-Type {content_type!r}")

            declared_len = int(resp.headers.get("Content-Length", 0) or 0)
            if declared_len and declared_len > config.max_image_bytes:
                raise ValueError(f"image too large ({declared_len} bytes)")

            dest_path = dest_dir / _filename_for(url, content_type, index)
            size = 0
            with open(dest_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > config.max_image_bytes:
                        fh.close()
                        dest_path.unlink(missing_ok=True)
                        raise ValueError("image exceeded size limit mid-stream")
                    fh.write(chunk)

            if size == 0:
                dest_path.unlink(missing_ok=True)
                raise ValueError("empty response body")

            logger.debug("Saved %s (%d bytes)", dest_path.name, size)
            return dest_path

        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            wait = config.retry_backoff * attempt
            logger.warning(
                "Attempt %d/%d failed for %s: %s%s",
                attempt,
                config.max_retries,
                url,
                exc,
                f" - retrying in {wait:.1f}s" if attempt < config.max_retries else "",
            )
            if attempt < config.max_retries:
                time.sleep(wait)

    raise RuntimeError(f"giving up on {url}: {last_exc}")


def scrape_images(
    urls: list[str],
    output_dir: Path | str,
    config: PipelineConfig | None = None,
) -> ScrapeResult:
    """Download every URL in ``urls`` into ``output_dir``.

    Never raises for an individual failed download - failures are collected
    in :attr:`ScrapeResult.failed`. Raises only if ``urls`` is empty.
    """
    config = config or PipelineConfig()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not urls:
        raise ValueError("scrape_images() received an empty URL list")

    result = ScrapeResult(output_dir=output_dir)
    logger.info("Starting download of %d image URL(s) -> %s", len(urls), output_dir)

    with requests.Session() as session:
        for i, url in enumerate(urls, start=1):
            try:
                path = download_image(url, output_dir, i, config, session)
                result.downloaded.append(path)
            except Exception as exc:  # noqa: BLE001 - we want to keep going
                logger.error("Download failed for %s: %s", url, exc)
                result.failed.append((url, str(exc)))

    logger.info(
        "Download complete: %d succeeded, %d failed",
        result.success_count,
        result.failure_count,
    )
    return result

"""NHS Digital publication page scraping and crime archive URLs.

NHS Digital pages are server-side rendered (no JS needed). Uses httpx +
BeautifulSoup. Download links follow: https://files.digital.nhs.uk/{hex}/{hex}/{filename}
No authentication required.

Police.uk crime archives use deterministic URLs: https://data.police.uk/data/archive/YYYY-MM.zip
"""

from pathlib import Path

import httpx
from bs4 import BeautifulSoup

QOF_BASE_PATH = (
    "/data-and-information/publications/statistical/"
    "quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data"
)

GP_PATIENTS_BASE_PATH = (
    "/data-and-information/publications/statistical/"
    "patients-registered-at-a-gp-practice"
)

NHS_DIGITAL_HOST = "https://digital.nhs.uk"


def _parse_publication_links(html: str, base_path: str) -> dict[str, str]:
    """Extract publication links from an NHS Digital listing page."""
    soup = BeautifulSoup(html, "html.parser")
    results = {}
    for uipath in ["ps.series.publications-list.latest", "ps.series.publications-list.previous"]:
        ul = soup.find("ul", attrs={"data-uipath": uipath})
        if not ul:
            continue
        for a in ul.find_all("a", href=True):
            href = a["href"]
            if href.startswith(base_path + "/"):
                slug = href[len(base_path) + 1:]
                results[slug] = NHS_DIGITAL_HOST + href
    return results


def _parse_download_links(html: str) -> list[dict]:
    """Extract download links from an NHS Digital publication page."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for a in soup.find_all("a", href=lambda h: h and "files.digital.nhs.uk" in h):
        href = a["href"]
        text = a.get_text(strip=True)
        is_zip = href.lower().endswith(".zip")
        is_csv_zip = is_zip and "csv" in text.lower()
        results.append({
            "url": href,
            "text": text,
            "is_zip": is_zip,
            "is_csv_zip": is_csv_zip,
        })
    return results


async def scrape_qof_year_urls() -> dict[str, str]:
    """Scrape the QOF publications listing page to find per-year page URLs.

    Returns:
        Dict mapping year slugs (e.g. "2024-25") to full publication URLs.
    """
    url = NHS_DIGITAL_HOST + QOF_BASE_PATH
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return _parse_publication_links(resp.text, QOF_BASE_PATH)


async def scrape_download_urls(publication_url: str) -> list[dict]:
    """Scrape download links from an NHS Digital publication page.

    Args:
        publication_url: Full URL of a specific publication page.

    Returns:
        List of dicts with keys: url, text, is_zip, is_csv_zip.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(publication_url)
        resp.raise_for_status()
    return _parse_download_links(resp.text)


async def find_qof_csv_zip_url(publication_url: str) -> str | None:
    """Find the raw CSV ZIP download URL on a QOF publication page.

    Args:
        publication_url: Full URL of a QOF year page.

    Returns:
        URL of the CSV ZIP file, or None if not found.
    """
    downloads = await scrape_download_urls(publication_url)
    csv_zips = [d for d in downloads if d["is_csv_zip"]]
    if csv_zips:
        return csv_zips[0]["url"]
    # Fallback: any ZIP file
    zips = [d for d in downloads if d["is_zip"]]
    if zips:
        return zips[0]["url"]
    return None


async def scrape_gp_catchment_urls() -> dict[str, str]:
    """Scrape the GP patients listing page to find per-month page URLs.

    Returns:
        Dict mapping month-year slugs to full publication URLs.
    """
    url = NHS_DIGITAL_HOST + GP_PATIENTS_BASE_PATH
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    return _parse_publication_links(resp.text, GP_PATIENTS_BASE_PATH)


async def download_file(url: str, dest: Path, print=print) -> None:
    """Download a file with progress reporting.

    Args:
        url: URL to download.
        dest: Local path to save to.
    """
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0 and downloaded % (10 * 1024 * 1024) < 65536:
                        pct = downloaded / total * 100
                        print(f"    {downloaded / 1024 / 1024:.0f} / {total / 1024 / 1024:.0f} MB ({pct:.0f}%)")


def crime_archive_url(year: int, month: int) -> str:
    """Construct a police.uk crime archive URL.

    Args:
        year: Year (e.g. 2024).
        month: Month (1-12).

    Returns:
        Archive URL like https://data.police.uk/data/archive/2024-01.zip
    """
    return f"https://data.police.uk/data/archive/{year}-{month:02d}.zip"

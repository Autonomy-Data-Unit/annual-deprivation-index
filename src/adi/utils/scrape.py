"""NHS Digital publication page scraping.

Pages are server-side rendered (no JS needed). Uses requests + BeautifulSoup
to extract download URLs. Download links follow the pattern:
    https://files.digital.nhs.uk/{hex}/{hex}/{filename}
No authentication required.
"""

import requests
from bs4 import BeautifulSoup

QOF_PUBLICATIONS_URL = (
    "https://digital.nhs.uk/data-and-information/publications/statistical/"
    "quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data"
)

GP_PATIENTS_PUBLICATIONS_URL = (
    "https://digital.nhs.uk/data-and-information/publications/statistical/"
    "patients-registered-at-a-gp-practice"
)


def scrape_publication_download_urls(publication_url: str) -> list[dict]:
    """Scrape download links from an NHS Digital publication page.

    Args:
        publication_url: Full URL of a specific publication page,
            e.g. "https://digital.nhs.uk/.../2024-25".

    Returns:
        List of dicts with keys: url, filename, filetype, size.
    """
    raise NotImplementedError


def scrape_qof_year_urls() -> dict[str, str]:
    """Scrape the QOF publications listing page to find per-year page URLs.

    Returns:
        Dict mapping year slugs (e.g. "2024-25") to full publication page URLs.
    """
    raise NotImplementedError


def scrape_gp_catchment_urls() -> dict[str, str]:
    """Scrape the GP patients listing page to find per-month page URLs.

    Returns:
        Dict mapping month-year slugs (e.g. "april-2025") to full page URLs.
    """
    raise NotImplementedError

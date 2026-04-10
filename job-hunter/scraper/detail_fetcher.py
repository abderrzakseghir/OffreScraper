"""
Detail Fetcher — Récupère la description complète d'une offre
en naviguant vers sa page individuelle.
"""

import asyncio
import logging
from bs4 import BeautifulSoup
from scraper.crawler import Crawler

HTML_PARSER = "html.parser"

logger = logging.getLogger(__name__)


async def fetch_offre_detail(crawler: Crawler, url: str, source: str) -> str:
    """Récupère la description complète d'une offre depuis sa page individuelle."""
    if not url:
        return ""

    html = await crawler.fetch_page(url)
    if not html:
        return ""

    source_lower = source.lower()

    if "linkedin" in source_lower:
        return _extract_linkedin_detail(html)
    elif "indeed" in source_lower:
        return _extract_indeed_detail(html)
    elif "welcome" in source_lower:
        return _extract_wttj_detail(html)
    else:
        return _extract_generic_detail(html)


def _extract_linkedin_detail(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        "div.show-more-less-html__markup",
        "div.description__text",
        "section.show-more-less-html",
        "div[class*='description']",
    ]
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 50:
                return text[:3000]
    return ""


def _extract_indeed_detail(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        "div#jobDescriptionText",
        "div.jobsearch-jobDescriptionText",
        "div[class*='jobDescription']",
    ]
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 50:
                return text[:3000]
    return ""


def _extract_wttj_detail(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        "div[data-testid='job-section-description']",
        "div[class*='JobDescription']",
        "section[class*='description']",
        "div[class*='content'] div[class*='description']",
    ]
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 50:
                return text[:3000]
    return ""


def _extract_generic_detail(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Chercher les plus gros blocs de texte
    candidates = []
    for tag in soup.find_all(["div", "section", "article"]):
        text = tag.get_text(separator="\n", strip=True)
        if 200 < len(text) < 5000:
            candidates.append(text)

    if candidates:
        # Retourner le plus long
        return max(candidates, key=len)[:3000]
    return ""


async def enrich_offres_with_details(crawler: Crawler, offres: list[dict],
                                     max_concurrent: int = 3) -> list[dict]:
    """
    Enrichit les offres avec leur description complète.
    Limite la concurrence pour éviter les blocages.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(offre: dict) -> dict:
        if offre.get("description") and len(offre["description"]) > 100:
            return offre  # Description déjà suffisante

        async with semaphore:
            description = await fetch_offre_detail(
                crawler,
                offre.get("url", ""),
                offre.get("source", ""),
            )
            if description:
                offre["description"] = description
                logger.info("Description enrichie pour : %s (%d chars)",
                            offre.get("titre", ""), len(description))
            return offre

    tasks = [fetch_one(offre) for offre in offres]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    enriched = []
    for r in results:
        if isinstance(r, dict):
            enriched.append(r)
        else:
            logger.error("Erreur enrichissement : %s", r)

    logger.info("Offres enrichies : %d/%d", len(enriched), len(offres))
    return enriched

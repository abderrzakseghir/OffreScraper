"""
Crawler Playwright — Parcourt les URLs sources et récupère le HTML brut.
Utilise playwright-stealth pour contourner les cookies/détections.
Rotation de user-agents et délais humains pour éviter les blocages.
"""

import asyncio
import random
import logging
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser
from playwright_stealth import stealth_async
import yaml

logger = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Crawler:
    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        scraping_cfg = self.config.get("scraping", {})
        self.headless = scraping_cfg.get("headless", True)
        self.delai_min = scraping_cfg.get("delai_min_secondes", 2)
        self.delai_max = scraping_cfg.get("delai_max_secondes", 5)
        self.max_pages = scraping_cfg.get("max_pages_par_source", 5)
        self.user_agents = scraping_cfg.get("user_agents", [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ])
        self.browser: Browser | None = None

    def _random_user_agent(self) -> str:
        return random.choice(self.user_agents)

    async def _human_delay(self):
        delay = random.uniform(self.delai_min, self.delai_max)
        await asyncio.sleep(delay)

    async def start(self):
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(headless=self.headless)
        logger.info("Navigateur lancé (headless=%s)", self.headless)

    async def stop(self):
        if self.browser:
            await self.browser.close()
        await self._playwright.stop()
        logger.info("Navigateur fermé")

    async def fetch_page(self, url: str) -> str:
        """Récupère le contenu HTML d'une page avec stealth et délai humain."""
        context = await self.browser.new_context(
            user_agent=self._random_user_agent(),
            viewport={"width": 1920, "height": 1080},
            locale="fr-FR",
        )
        page: Page = await context.new_page()
        await stealth_async(page)

        try:
            logger.info("Navigation vers %s", url)
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await self._human_delay()

            # Tenter de fermer les popups cookies courants
            await self._dismiss_cookie_banners(page)

            # Scroll pour charger le contenu lazy-loaded
            await self._scroll_page(page)

            content = await page.content()
            logger.info("Page récupérée : %d caractères", len(content))
            return content
        except Exception as e:
            logger.error("Erreur lors du fetch de %s : %s", url, e)
            return ""
        finally:
            await context.close()

    async def _dismiss_cookie_banners(self, page: Page):
        """Tente de cliquer sur les boutons d'acceptation de cookies."""
        selectors = [
            'button:has-text("Accepter")',
            'button:has-text("Accept")',
            'button:has-text("Tout accepter")',
            'button:has-text("Accept all")',
            'button:has-text("J\'accepte")',
            '[id*="cookie"] button',
            '[class*="cookie"] button',
            '[data-testid="cookie-banner"] button',
        ]
        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    logger.info("Cookie banner fermé via : %s", selector)
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                continue

    async def _scroll_page(self, page: Page, scrolls: int = 3):
        """Scroll progressif pour déclencher le chargement lazy."""
        for _ in range(scrolls):
            await page.evaluate("window.scrollBy(0, window.innerHeight)")
            await asyncio.sleep(random.uniform(0.5, 1.5))

    async def crawl_sources(self) -> list[dict]:
        """Parcourt toutes les sources actives via les adaptateurs dédiés."""
        sources = self.config.get("sources", [])
        results = []

        for source in sources:
            if not source.get("actif", False):
                continue

            nom = source["nom"]
            url = source["url"]
            logger.info("=== Crawl de %s ===", nom)

            pages_html = await self._crawl_with_adapter(nom, url)

            for html in pages_html:
                if html:
                    results.append({
                        "source": nom,
                        "url": url,
                        "html": html,
                    })

        logger.info("Crawl terminé : %d pages récupérées", len(results))
        return results

    async def _crawl_with_adapter(self, source_name: str, url: str) -> list[str]:
        """Utilise l'adaptateur dédié si disponible, sinon fetch simple."""
        name_lower = source_name.lower()

        try:
            if "linkedin" in name_lower:
                from scraper.sites.linkedin import crawl_linkedin
                return await crawl_linkedin(self, url, self.max_pages)
            elif "indeed" in name_lower:
                from scraper.sites.indeed import crawl_indeed
                return await crawl_indeed(self, url, self.max_pages)
            elif "welcome" in name_lower or "wttj" in name_lower:
                from scraper.sites.welcometothejungle import crawl_wttj
                return await crawl_wttj(self, url, self.max_pages)
        except Exception as e:
            logger.warning("Adaptateur %s échoué, fallback fetch simple : %s", source_name, e)

        # Fallback : fetch simple d'une seule page
        html = await self.fetch_page(url)
        return [html] if html else []


async def run_crawler(config: dict | None = None) -> list[dict]:
    crawler = Crawler(config)
    await crawler.start()
    try:
        return await crawler.crawl_sources()
    finally:
        await crawler.stop()


async def run_crawler_with_details(config: dict | None = None) -> tuple:
    """Crawle les sources ET récupère les descriptions complètes des offres."""
    from scraper.extractor import extract_all
    from scraper.detail_fetcher import enrich_offres_with_details

    crawler = Crawler(config)
    await crawler.start()
    try:
        # Phase 1a : Crawl des listings
        crawl_results = await crawler.crawl_sources()

        # Phase 1b : Extraction des offres
        offres = extract_all(crawl_results, config)

        # Phase 1c : Enrichissement avec descriptions complètes
        offres_dicts = [
            {
                "titre": o.titre,
                "entreprise": o.entreprise,
                "localisation": o.localisation,
                "description": o.description,
                "url": o.url,
                "source": o.source,
                "type_contrat": o.type_contrat,
                "date_publication": o.date_publication,
                "technologies": o.technologies,
            }
            for o in offres
        ]
        enriched = await enrich_offres_with_details(crawler, offres_dicts)
        return crawl_results, enriched
    finally:
        await crawler.stop()

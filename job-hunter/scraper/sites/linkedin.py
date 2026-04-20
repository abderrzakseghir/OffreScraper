"""
Adaptateur LinkedIn — Logique spécifique au crawl LinkedIn.
"""

import logging
from scraper.crawler import Crawler

logger = logging.getLogger(__name__)

# Sélecteurs CSS spécifiques LinkedIn (page publique)
LINKEDIN_SELECTORS = {
    "job_card": "div.base-card, li.result-card, div.job-search-card",
    "title": "h3.base-search-card__title",
    "company": "h4.base-search-card__subtitle",
    "location": "span.job-search-card__location",
    "link": "a.base-card__full-link",
    "date": "time",
    "load_more": "button[aria-label='Charger plus de résultats']",
}


async def crawl_linkedin(crawler: Crawler, url: str, max_pages: int = 3) -> list[str]:
    """Crawle LinkedIn avec pagination via scroll/bouton 'Charger plus'."""
    pages_html = []

    context = await crawler.browser.new_context(
        user_agent=crawler._random_user_agent(),
        viewport={"width": 1920, "height": 1080},
        locale="fr-FR",
    )
    page = await context.new_page()
    from playwright_stealth import stealth_async
    await stealth_async(page)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await crawler._human_delay()
        await crawler._dismiss_cookie_banners(page)

        for i in range(max_pages):
            logger.info("LinkedIn page %d/%d", i + 1, max_pages)
            await crawler._scroll_page(page, scrolls=5)

            html = await page.content()
            pages_html.append(html)

            # Cliquer sur "Voir plus" si disponible
            try:
                btn = page.locator(LINKEDIN_SELECTORS["load_more"]).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await crawler._human_delay()
                else:
                    break
            except Exception:
                break

    except Exception as e:
        logger.error("Erreur crawl LinkedIn : %s", e)
    finally:
        await context.close()

    return pages_html

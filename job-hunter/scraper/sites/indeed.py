"""
Adaptateur Indeed — Logique spécifique au crawl Indeed.
"""

import logging
from scraper.crawler import Crawler

logger = logging.getLogger(__name__)

INDEED_SELECTORS = {
    "job_card": "div.job_seen_beacon",
    "title": "h2.jobTitle span",
    "company": "span[data-testid='company-name']",
    "location": "div[data-testid='text-location']",
    "link": "a[data-jk]",
    "next_page": "a[data-testid='pagination-page-next']",
}


async def crawl_indeed(crawler: Crawler, url: str, max_pages: int = 3) -> list[str]:
    """Crawle Indeed avec pagination via le bouton 'Suivant'."""
    pages_html = []
    current_url = url

    context = await crawler._stealth.use_async(
        crawler.browser.new_context(
            user_agent=crawler._random_user_agent(),
            viewport={"width": 1920, "height": 1080},
            locale="fr-FR",
        )
    )
    page = await context.new_page()

    try:
        for i in range(max_pages):
            logger.info("Indeed page %d/%d — %s", i + 1, max_pages, current_url)

            await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
            await crawler._human_delay()

            if i == 0:
                await crawler._dismiss_cookie_banners(page)

            await crawler._scroll_page(page)
            html = await page.content()
            pages_html.append(html)

            # Pagination
            try:
                next_btn = page.locator(INDEED_SELECTORS["next_page"]).first
                if await next_btn.is_visible(timeout=2000):
                    href = await next_btn.get_attribute("href")
                    if href:
                        current_url = "https://fr.indeed.com" + href if not href.startswith("http") else href
                    else:
                        break
                else:
                    break
            except Exception:
                break

    except Exception as e:
        logger.error("Erreur crawl Indeed : %s", e)
    finally:
        await context.close()

    return pages_html

"""
Adaptateur Welcome to the Jungle — Logique spécifique au crawl WTTJ.
"""

import logging
from scraper.crawler import Crawler

logger = logging.getLogger(__name__)

WTTJ_SELECTORS = {
    "job_card": "li[data-testid='search-results-list-item-wrapper']",
    "title": "h4, [class*='title']",
    "company": "span[class*='company'], h3",
    "location": "span[class*='location']",
    "contract": "span[class*='contract']",
    "link": "a[href*='/jobs/']",
    "next_page": "a[aria-label='Page suivante'], nav[aria-label='pagination'] a:last-child",
}


async def crawl_wttj(crawler: Crawler, url: str, max_pages: int = 3) -> list[str]:
    """Crawle Welcome to the Jungle avec pagination par URL."""
    pages_html = []
    current_url = url

    context = await crawler.browser.new_context(
        user_agent=crawler._random_user_agent(),
        viewport={"width": 1920, "height": 1080},
        locale="fr-FR",
    )
    page = await context.new_page()
    from playwright_stealth import stealth_async
    await stealth_async(page)

    try:
        for i in range(max_pages):
            logger.info("WTTJ page %d/%d — %s", i + 1, max_pages, current_url)

            await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
            await crawler._human_delay()

            if i == 0:
                await crawler._dismiss_cookie_banners(page)

            await crawler._scroll_page(page, scrolls=4)
            html = await page.content()
            pages_html.append(html)

            # Pagination via paramètre page dans l'URL
            try:
                next_btn = page.locator(WTTJ_SELECTORS["next_page"]).first
                if await next_btn.is_visible(timeout=2000):
                    href = await next_btn.get_attribute("href")
                    if href:
                        current_url = href if href.startswith("http") else "https://www.welcometothejungle.com" + href
                    else:
                        break
                else:
                    break
            except Exception:
                break

    except Exception as e:
        logger.error("Erreur crawl WTTJ : %s", e)
    finally:
        await context.close()

    return pages_html

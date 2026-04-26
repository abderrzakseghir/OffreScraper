"""
Bridge script — Called by the Next.js web app to run the EXACT same scraping
pipeline as 'python run.py scrape' (run_crawler_with_details).

Accepts JSON config on stdin, outputs scraped offers as JSON to stdout.

Usage:
    echo '{"custom_urls": [...], "search": {...}}' | python bridge_scrape.py
"""

import asyncio
import json
import sys
import io
import logging
from pathlib import Path

# Force UTF-8 stdout on Windows (évite erreur charmap avec emojis/caractères spéciaux)
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml
from scraper.crawler import run_crawler_with_details

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("bridge_scrape")


def build_config(input_data: dict) -> dict:
    """
    Build a config dict from config.yaml + optional overrides from the web app.
    Keeps config.yaml as the single source of truth (same as run.py).
    """
    config_path = Path(__file__).resolve().parent / "config.yaml"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    # ── Additional custom URLs from the web app settings ──
    custom_urls = input_data.get("custom_urls", [])
    existing_urls = {s["url"] for s in config.get("sources", []) if s.get("actif")}

    for url in custom_urls:
        url = url.strip()
        if not url or url in existing_urls:
            continue

        # Auto-detect source name from URL
        name = "Custom"
        url_lower = url.lower()
        if "linkedin" in url_lower:
            name = "LinkedIn"
        elif "indeed" in url_lower:
            name = "Indeed"
        elif "welcome" in url_lower or "wttj" in url_lower:
            name = "Welcome to the Jungle"
        elif "hellowork" in url_lower:
            name = "HelloWork"

        config.setdefault("sources", []).append({"nom": name, "url": url, "actif": True})

    # ── Override search params only if the web app provides non-empty values ──
    search = input_data.get("search", {})
    if search:
        recherche = config.get("recherche", {})
        if search.get("targetLocation"):
            recherche["localisation"] = [search["targetLocation"]]
        if search.get("includeKeywords"):
            recherche["mots_cles"] = search["includeKeywords"]
        if search.get("excludeKeywords"):
            recherche["mots_cles_exclusion"] = search["excludeKeywords"]
        if search.get("contractTypes"):
            recherche["type_contrat"] = search["contractTypes"][0]
        config["recherche"] = recherche

    return config


def main():
    # ── Read JSON from stdin ──
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        input_data = {}

    config = build_config(input_data)

    if not config.get("sources"):
        print(json.dumps([], ensure_ascii=False), flush=True)
        return

    try:
        # Call the EXACT same function as run.py phase1
        _crawl_results, enriched_offres = asyncio.run(run_crawler_with_details(config))

        # Output JSON to stdout — identical dict shape as run.py
        print(json.dumps(enriched_offres, ensure_ascii=False), flush=True)

    except Exception as e:
        logger.error("Scraping failed: %s", e)
        print(json.dumps({"error": str(e)}, ensure_ascii=False), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

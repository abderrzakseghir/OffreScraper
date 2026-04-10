"""
Extracteur d'offres — Parse le HTML brut et extrait les offres CDI.
Filtre selon les critères de recherche définis dans config.yaml.
"""

import re
import logging
from dataclasses import dataclass, field
from bs4 import BeautifulSoup
from pathlib import Path
import yaml

HTML_PARSER = "html.parser"

logger = logging.getLogger(__name__)


@dataclass
class Offre:
    titre: str = ""
    entreprise: str = ""
    localisation: str = ""
    description: str = ""
    url: str = ""
    source: str = ""
    type_contrat: str = ""
    date_publication: str = ""
    technologies: list[str] = field(default_factory=list)


def load_config() -> dict:
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Extractor:
    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        recherche = self.config.get("recherche", {})
        self.type_contrat = recherche.get("type_contrat", "CDI").lower()
        self.localisations = [l.lower() for l in recherche.get("localisation", [])]
        self.mots_cles = [m.lower() for m in recherche.get("mots_cles", [])]
        self.mots_exclusion = [m.lower() for m in recherche.get("mots_cles_exclusion", [])]

    def extract_offres(self, html: str, source: str, source_url: str) -> list[Offre]:
        """Extrait les offres depuis le HTML selon la source."""
        source_lower = source.lower()

        if "linkedin" in source_lower:
            return self._extract_linkedin(html, source)
        elif "indeed" in source_lower:
            return self._extract_indeed(html, source)
        elif "welcome" in source_lower:
            return self._extract_welcometothejungle(html, source)
        else:
            return self._extract_generic(html, source)

    def _extract_linkedin(self, html: str, source: str) -> list[Offre]:
        soup = BeautifulSoup(html, "html.parser")
        offres = []

        # LinkedIn job cards (page publique, non connecté)
        cards = soup.select("div.base-card, li.result-card, div.job-search-card")
        for card in cards:
            offre = Offre(source=source)

            titre_el = card.select_one("h3.base-search-card__title, h3.result-card__title")
            if titre_el:
                offre.titre = titre_el.get_text(strip=True)

            entreprise_el = card.select_one("h4.base-search-card__subtitle, h4.result-card__subtitle")
            if entreprise_el:
                offre.entreprise = entreprise_el.get_text(strip=True)

            lieu_el = card.select_one("span.job-search-card__location")
            if lieu_el:
                offre.localisation = lieu_el.get_text(strip=True)

            lien_el = card.select_one("a.base-card__full-link, a.result-card__full-link")
            if lien_el and lien_el.get("href"):
                offre.url = lien_el["href"].split("?")[0]

            date_el = card.select_one("time")
            if date_el:
                offre.date_publication = date_el.get("datetime", "")

            if self._is_relevant(offre):
                offres.append(offre)

        logger.info("LinkedIn : %d offres extraites", len(offres))
        return offres

    def _extract_indeed(self, html: str, source: str) -> list[Offre]:
        soup = BeautifulSoup(html, "html.parser")
        offres = []

        cards = soup.select("div.job_seen_beacon, div.jobsearch-ResultsList > div")
        for card in cards:
            offre = Offre(source=source)

            titre_el = card.select_one("h2.jobTitle span, a.jcs-JobTitle span")
            if titre_el:
                offre.titre = titre_el.get_text(strip=True)

            entreprise_el = card.select_one("span[data-testid='company-name'], span.companyName")
            if entreprise_el:
                offre.entreprise = entreprise_el.get_text(strip=True)

            lieu_el = card.select_one("div[data-testid='text-location'], div.companyLocation")
            if lieu_el:
                offre.localisation = lieu_el.get_text(strip=True)

            lien_el = card.select_one("a[data-jk], a.jcs-JobTitle")
            if lien_el and lien_el.get("href"):
                href = lien_el["href"]
                if not href.startswith("http"):
                    href = "https://fr.indeed.com" + href
                offre.url = href

            snippet_el = card.select_one("div.job-snippet, td.resultContent")
            if snippet_el:
                offre.description = snippet_el.get_text(strip=True)[:500]

            if self._is_relevant(offre):
                offres.append(offre)

        logger.info("Indeed : %d offres extraites", len(offres))
        return offres

    def _extract_welcometothejungle(self, html: str, source: str) -> list[Offre]:
        soup = BeautifulSoup(html, "html.parser")
        offres = []

        cards = soup.select("li[data-testid='search-results-list-item-wrapper'], div[class*='SearchResults'] li")
        for card in cards:
            offre = Offre(source=source)

            titre_el = card.select_one("h4, [class*='title']")
            if titre_el:
                offre.titre = titre_el.get_text(strip=True)

            entreprise_el = card.select_one("span[class*='company'], h3")
            if entreprise_el:
                offre.entreprise = entreprise_el.get_text(strip=True)

            lien_el = card.select_one("a[href*='/jobs/']")
            if lien_el and lien_el.get("href"):
                href = lien_el["href"]
                if not href.startswith("http"):
                    href = "https://www.welcometothejungle.com" + href
                offre.url = href

            offre.type_contrat = "CDI"

            if self._is_relevant(offre):
                offres.append(offre)

        logger.info("Welcome to the Jungle : %d offres extraites", len(offres))
        return offres

    def _extract_generic(self, html: str, source: str) -> list[Offre]:
        """Extraction générique basée sur des patterns communs."""
        soup = BeautifulSoup(html, "html.parser")
        offres = []

        # Chercher des liens de jobs par patterns d'URL
        links = soup.find_all("a", href=re.compile(r"(job|emploi|offre|career|poste)", re.I))
        seen_urls = set()

        for link in links:
            href = link.get("href", "")
            if href in seen_urls:
                continue
            seen_urls.add(href)

            offre = Offre(source=source)
            offre.titre = link.get_text(strip=True)
            offre.url = href

            if offre.titre and len(offre.titre) > 5:
                offres.append(offre)

        logger.info("Générique (%s) : %d liens d'offres trouvés", source, len(offres))
        return offres

    def _is_relevant(self, offre: Offre) -> bool:
        """Vérifie si l'offre correspond aux critères de recherche."""
        texte = f"{offre.titre} {offre.description} {offre.entreprise}".lower()

        # Exclure si mots d'exclusion présents
        for mot in self.mots_exclusion:
            if mot in texte:
                return False

        # Vérifier le type de contrat si spécifié dans l'offre
        if offre.type_contrat and self.type_contrat not in offre.type_contrat.lower():
            # L'offre mentionne un autre type de contrat → exclure
            if any(t in offre.type_contrat.lower() for t in ["stage", "cdd", "freelance", "interim"]):
                return False

        # On garde l'offre si on n'a pas pu déterminer le contrat
        return True

    def filter_cdi(self, offres: list[Offre]) -> list[Offre]:
        """Filtre supplémentaire pour ne garder que les CDI confirmés."""
        filtered = []
        for offre in offres:
            texte = f"{offre.titre} {offre.description} {offre.type_contrat}".lower()
            # Exclure les non-CDI explicites
            if any(t in texte for t in ["stage", "internship", "cdd", "freelance", "interim", "apprentissage"]):
                continue
            filtered.append(offre)
        return filtered


def extract_all(crawl_results: list[dict], config: dict | None = None) -> list[Offre]:
    """Extrait les offres de tous les résultats de crawl."""
    extractor = Extractor(config)
    all_offres = []

    for result in crawl_results:
        offres = extractor.extract_offres(
            html=result["html"],
            source=result["source"],
            source_url=result["url"],
        )
        all_offres.extend(offres)

    # Filtrage CDI final
    all_offres = extractor.filter_cdi(all_offres)

    # Dédoublonner par URL
    seen = set()
    unique = []
    for offre in all_offres:
        if offre.url and offre.url not in seen:
            seen.add(offre.url)
            unique.append(offre)
        elif not offre.url:
            unique.append(offre)

    logger.info("Total offres extraites et filtrées : %d", len(unique))
    return unique

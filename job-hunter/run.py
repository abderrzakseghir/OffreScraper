"""
Job Hunter — Point d'entrée principal.
Orchestre les 4 phases : scraping, matching IA, génération CV, stockage.

Usage:
    python run.py              # Toutes les phases
    python run.py scrape       # Phase 1 uniquement
    python run.py match        # Phase 2 uniquement
    python run.py cv           # Phase 3 uniquement
    python run.py lettre       # Générer les lettres de motivation
    python run.py dashboard    # Lancer le dashboard Flask
"""

import asyncio
import sys
import os
import logging
import argparse
from pathlib import Path

# Ajouter le répertoire courant au path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Charger .env si présent
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

from scraper.crawler import run_crawler_with_details
from ai.matcher import score_offre
from ai.cv_generator import generate_cv_for_offre
from ai.lettre_generator import generate_lettre, save_lettre
from db.database import (
    init_db,
    insert_offre,
    get_offres,
    insert_score,
    insert_cv,
    update_offre_statut,
    get_stats,
    get_offres_with_scores,
    get_score_for_offre,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("job-hunter")


async def phase1_scraping(config=None):
    """Phase 1 — Scraper les offres avec descriptions complètes."""
    logger.info("═══ PHASE 1 : Scraping des offres ═══")

    # Crawl avec enrichissement des descriptions
    _crawl_results, enriched_offres = await run_crawler_with_details(config)

    if not enriched_offres:
        logger.warning("Aucune offre récupérée.")
        return []

    logger.info("Offres extraites et enrichies : %d", len(enriched_offres))

    # Stockage en BD
    inserted = 0
    for offre in enriched_offres:
        offre_id = insert_offre(offre)
        if offre_id:
            inserted += 1

    logger.info("Nouvelles offres insérées en BD : %d", inserted)
    return enriched_offres


def phase2_matching(score_minimum: int = 30):
    """Phase 2 — Scorer les offres non encore scorées via l'IA."""
    logger.info("═══ PHASE 2 : Matching IA ═══")

    offres = get_offres(statut="nouveau")
    logger.info("Offres à scorer : %d", len(offres))

    if not offres:
        logger.info("Aucune nouvelle offre à scorer.")
        return

    scored = 0
    for offre in offres:
        logger.info("Scoring : %s — %s", offre["titre"], offre["entreprise"])
        result = score_offre(
            offre_titre=offre["titre"],
            offre_description=offre["description"],
            offre_entreprise=offre["entreprise"],
        )
        insert_score(offre["id"], result)
        update_offre_statut(offre["id"], "vu")
        scored += 1

        score_val = result.get("score", 0)
        if score_val >= score_minimum:
            logger.info("  → Score %d/100 — Éligible pour CV", score_val)
        else:
            logger.info("  → Score %d/100 — En dessous du seuil", score_val)
        
        import time
        time.sleep(3)  # Anti rate-limit de 3 secondes entre les calls


    logger.info("Offres scorées : %d", scored)


def phase3_cv_generation(score_minimum: int = 50):
    """Phase 3 — Générer des CVs personnalisés pour les offres au-dessus du seuil."""
    logger.info("═══ PHASE 3 : Génération de CV ═══")

    offres = get_offres_with_scores()
    candidates = [
        o for o in offres
        if (o.get("score") or 0) >= score_minimum and not o.get("pdf_path")
    ]

    logger.info("Offres éligibles pour CV (score >= %d) : %d", score_minimum, len(candidates))

    if not candidates:
        logger.info("Aucune offre éligible.")
        return

    generated = 0
    for offre in candidates:
        logger.info("Génération CV pour : %s — %s", offre["titre"], offre["entreprise"])
        score_data = get_score_for_offre(offre["id"])
        result = generate_cv_for_offre(offre, score_data)

        if result["success"]:
            insert_cv(offre["id"], result)
            generated += 1
            logger.info("  → CV généré : %s", result.get("pdf_path", ""))
        else:
            logger.warning("  → Échec : %s", result.get("error", ""))
            
        import time
        time.sleep(3)  # Anti rate-limit de 3 secondes entre les calls

    logger.info("CVs générés : %d", generated)


def phase3b_lettre_generation(score_minimum: int = 60):
    """Phase 3b — Générer des lettres de motivation pour les meilleures offres."""
    logger.info("═══ PHASE 3b : Génération de lettres de motivation ═══")

    offres = get_offres_with_scores()
    candidates = [o for o in offres if (o.get("score") or 0) >= score_minimum]

    logger.info("Offres éligibles pour lettres (score >= %d) : %d", score_minimum, len(candidates))

    generated = 0
    for offre in candidates:
        logger.info("Lettre pour : %s — %s", offre["titre"], offre["entreprise"])
        score_data = get_score_for_offre(offre["id"])
        lettre = generate_lettre(
            offre_titre=offre.get("titre", ""),
            offre_description=offre.get("description", ""),
            offre_entreprise=offre.get("entreprise", ""),
            score_data=score_data,
        )
        if lettre:
            path = save_lettre(lettre, offre.get("entreprise", ""), offre.get("titre", ""))
            generated += 1
            logger.info("  → Lettre générée : %s", path)
        else:
            logger.warning("  → Échec génération lettre")

    logger.info("Lettres générées : %d", generated)


def phase4_dashboard():
    """Phase 4 — Lancer le dashboard Flask."""
    logger.info("═══ PHASE 4 : Dashboard ═══")
    stats = get_stats()
    logger.info("Stats actuelles : %s", stats)

    from dashboard.app import app
    logger.info("Dashboard démarré sur http://localhost:5000")
    app.run(debug=True, port=5000, use_reloader=False)


async def run_all(score_minimum: int = 50):
    """Exécute les phases 1 à 3 séquentiellement."""
    init_db()

    # Phase 1 : Scraping + enrichissement descriptions
    await phase1_scraping()

    # Phase 2 : Matching IA
    phase2_matching(score_minimum=30)

    # Phase 3 : Génération CV
    phase3_cv_generation(score_minimum=score_minimum)

    # Phase 3b : Lettres de motivation
    phase3b_lettre_generation(score_minimum=60)

    # Résumé final
    stats = get_stats()
    logger.info("═══ RÉSUMÉ FINAL ═══")
    logger.info("  Offres totales : %d", stats["total_offres"])
    logger.info("  Offres scorées : %d", stats["offres_scorees"])
    logger.info("  CVs générés   : %d", stats["cvs_generes"])
    logger.info("  Score moyen   : %.1f/100", stats["score_moyen"])
    logger.info("")
    logger.info("Lancez 'python run.py dashboard' pour voir le tableau de bord.")


def main():
    parser = argparse.ArgumentParser(
        description="Job Hunter — Automatisation de recherche d'emploi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python run.py              # Exécuter toutes les phases
  python run.py scrape       # Scraper les offres uniquement
  python run.py match        # Scorer les offres avec l'IA
  python run.py cv           # Générer les CVs personnalisés
  python run.py lettre       # Générer les lettres de motivation
  python run.py dashboard    # Lancer le tableau de bord web
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["all", "scrape", "match", "cv", "lettre", "dashboard"],
        help="Phase à exécuter (default: all)",
    )
    parser.add_argument(
        "--score-min",
        type=int,
        default=50,
        help="Score minimum pour générer un CV (default: 50)",
    )
    args = parser.parse_args()

    init_db()

    if args.command == "all":
        asyncio.run(run_all(args.score_min))
    elif args.command == "scrape":
        asyncio.run(phase1_scraping())
    elif args.command == "match":
        phase2_matching()
    elif args.command == "cv":
        phase3_cv_generation(args.score_min)
    elif args.command == "lettre":
        phase3b_lettre_generation(score_minimum=args.score_min)
    elif args.command == "dashboard":
        phase4_dashboard()


if __name__ == "__main__":
    main()

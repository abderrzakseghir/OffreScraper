"""
Générateur de lettre de motivation — Crée une lettre personnalisée par offre via Claude.
"""

import os
import logging
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_api_key(config: dict) -> str:
    key = config.get("anthropic", {}).get("api_key", "")
    if key.startswith("${") and key.endswith("}"):
        env_var = key[2:-1]
        key = os.environ.get(env_var, "")
    if not key:
        raise ValueError("Clé API Anthropic manquante.")
    return key


def _build_profil_summary(config: dict) -> str:
    profil = config.get("profil", {})
    competences = ", ".join(profil.get("competences", []))

    experiences = ""
    for exp in profil.get("experience", []):
        experiences += f"- {exp['poste']} chez {exp['entreprise']} ({exp['periode']})\n"

    return f"""
Nom : {profil.get('nom', '')}
Titre : {profil.get('titre', '')}
Statut : {profil.get('statut', '')}
Compétences : {competences}

Expérience :
{experiences}
""".strip()


def generate_lettre(offre_titre: str, offre_description: str, offre_entreprise: str,
                    score_data: dict | None = None, config: dict | None = None) -> str:
    """Génère une lettre de motivation personnalisée."""
    import anthropic

    config = config or load_config()
    api_key = _get_api_key(config)
    model = config.get("anthropic", {}).get("model", "claude-sonnet-4-20250514")

    client = anthropic.Anthropic(api_key=api_key)
    profil = _build_profil_summary(config)

    conseil = ""
    if score_data:
        comp = score_data.get('competences_matchees', [])
        if isinstance(comp, str):
            comp = [c.strip() for c in comp.split(",") if c.strip()]
        conseil = f"Compétences matchées : {', '.join(comp)}"

    prompt = f"""Tu es un expert en rédaction de lettres de motivation pour des développeurs.

{profil}

OFFRE D'EMPLOI :
Titre : {offre_titre}
Entreprise : {offre_entreprise}
Description : {offre_description}

{conseil}

INSTRUCTIONS :
1. Rédige une lettre de motivation professionnelle et personnalisée
2. Mets en avant les compétences et expériences pertinentes pour cette offre
3. Montre ta motivation et ta connaissance de l'entreprise
4. Reste concis (300-400 mots maximum)
5. Ne mens JAMAIS — adapte uniquement la présentation
6. Ton professionnel mais pas trop formel
7. Structure : accroche → parcours pertinent → motivation → conclusion

Réponds UNIQUEMENT avec le texte de la lettre, sans commentaires ni balises."""

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        lettre = response.content[0].text.strip()
        logger.info("Lettre générée pour '%s' (%d chars)", offre_titre, len(lettre))
        return lettre
    except Exception as e:
        logger.error("Erreur génération lettre pour '%s' : %s", offre_titre, e)
        return ""


def save_lettre(lettre: str, entreprise: str, titre: str) -> Path:
    """Sauvegarde la lettre en fichier texte."""
    output_dir = Path(__file__).resolve().parent.parent / "latex" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"LM_{entreprise}_{titre}")
    path = output_dir / f"{safe_name}.txt"

    with open(path, "w", encoding="utf-8") as f:
        f.write(lettre)

    logger.info("Lettre sauvegardée : %s", path)
    return path

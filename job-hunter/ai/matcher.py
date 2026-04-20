"""
Matcher IA — Score de correspondance entre le profil candidat et une offre.
Utilise l'API OpenAI (ChatGPT) pour analyser la pertinence.
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
    key = config.get("openai", {}).get("api_key", "")
    if key.startswith("${") and key.endswith("}"):
        env_var = key[2:-1]
        key = os.environ.get(env_var, "")
    if not key:
        raise ValueError(
            "Clé API OpenAI manquante. "
            "Définissez la clé directement ou utilisez OPENAI_API_KEY."
        )
    return key


def _build_profil_prompt(config: dict) -> str:
    profil = config.get("profil", {})
    competences = ", ".join(profil.get("competences", []))

    experiences = ""
    for exp in profil.get("experience", []):
        experiences += f"- {exp['poste']} chez {exp['entreprise']} ({exp['periode']})\n"

    formations = ""
    for f in profil.get("formation", []):
        formations += f"- {f['diplome']} — {f['ecole']} ({f['periode']})\n"

    return f"""
PROFIL CANDIDAT :
Nom : {profil.get('nom', '')}
Titre : {profil.get('titre', '')}
Statut : {profil.get('statut', '')}
Objectif : {profil.get('objectif', '')}

Compétences : {competences}

Expérience :
{experiences}

Formation :
{formations}
""".strip()


def score_offre(offre_titre: str, offre_description: str, offre_entreprise: str,
                config: dict | None = None) -> dict:
    """
    Calcule un score de matching entre le profil et une offre.
    Retourne un dict avec : score (0-100), justification, competences_matchees, lacunes.
    """
    import openai

    config = config or load_config()
    api_key = _get_api_key(config)
    model = config.get("openai", {}).get("model", "gpt-4o")

    client = openai.OpenAI(api_key=api_key)

    profil_prompt = _build_profil_prompt(config)

    prompt = f"""Tu es un expert en recrutement IT. Analyse la correspondance entre le profil candidat et l'offre d'emploi.

{profil_prompt}

OFFRE D'EMPLOI :
Titre : {offre_titre}
Entreprise : {offre_entreprise}
Description : {offre_description}

Réponds UNIQUEMENT au format JSON suivant (pas de markdown, pas de commentaires) :
{{
    "score": <entier de 0 à 100>,
    "justification": "<explication courte de 2-3 phrases>",
    "competences_matchees": ["comp1", "comp2"],
    "lacunes": ["lacune1", "lacune2"],
    "conseil": "<conseil pour personnaliser la candidature>"
}}"""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        import json
        text = response.choices[0].message.content.strip()
        # Nettoyer si wrapped dans des backticks
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
        logger.info("Score pour '%s' : %d/100", offre_titre, result.get("score", 0))
        return result
    except Exception as e:
        logger.error("Erreur scoring pour '%s' : %s", offre_titre, e)
        return {
            "score": 0,
            "justification": f"Erreur lors de l'analyse : {e}",
            "competences_matchees": [],
            "lacunes": [],
            "conseil": "",
        }


def score_offres_batch(offres: list[dict], config: dict | None = None) -> list[dict]:
    """Score un lot d'offres. Chaque offre doit avoir titre, description, entreprise."""
    results = []
    for offre in offres:
        result = score_offre(
            offre_titre=offre.get("titre", ""),
            offre_description=offre.get("description", ""),
            offre_entreprise=offre.get("entreprise", ""),
            config=config,
        )
        result["offre_titre"] = offre.get("titre", "")
        result["offre_url"] = offre.get("url", "")
        results.append(result)
    return results

"""
Bridge script — Called by the Next.js web app to generate CV or cover letter LaTeX.
Accepts JSON on stdin with action + offer data, outputs LaTeX as JSON to stdout.

Usage:
    echo '{"action": "cv", "offer": {...}, "profile": {...}, "api_key": "..."}' | python bridge_generate.py
    echo '{"action": "cover-letter", "offer": {...}, "profile": {...}, "api_key": "..."}' | python bridge_generate.py
"""

import json
import sys
import os
import io
import logging
from pathlib import Path

# Force UTF-8 stdout on Windows
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s", stream=sys.stderr)
logger = logging.getLogger("bridge_generate")


def build_config(input_data: dict) -> dict:
    """Build config compatible with existing generators."""
    import yaml
    config_path = Path(__file__).resolve().parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    # Override API key if provided
    api_key = input_data.get("api_key", "")
    if api_key:
        if "openai" not in config:
            config["openai"] = {}
        config["openai"]["api_key"] = api_key

    # Override profile if provided
    profile = input_data.get("profile", {})
    if profile:
        config["profil"] = {
            "nom": profile.get("name", ""),
            "titre": profile.get("targetJobTitle", ""),
            "statut": profile.get("educationLevel", ""),
            "objectif": profile.get("bio", ""),
            "competences": profile.get("skills", []),
            "experience": [],
            "formation": [],
        }

    return config


def generate_cv(input_data: dict) -> dict:
    from ai.cv_generator import generate_cv_latex
    config = build_config(input_data)
    offer = input_data.get("offer", {})

    latex = generate_cv_latex(
        offre_titre=offer.get("title", ""),
        offre_description=offer.get("description", ""),
        offre_entreprise=offer.get("company", ""),
        score_data=None,
        config=config,
    )

    if latex:
        return {"success": True, "latex": latex}
    return {"success": False, "error": "Génération LaTeX échouée"}


def generate_cover_letter(input_data: dict) -> dict:
    from ai.lettre_generator import generate_lettre
    config = build_config(input_data)
    offer = input_data.get("offer", {})

    lettre = generate_lettre(
        offre_titre=offer.get("title", ""),
        offre_description=offer.get("description", ""),
        offre_entreprise=offer.get("company", ""),
        score_data=None,
        config=config,
    )

    if lettre:
        return {"success": True, "latex": lettre}
    return {"success": False, "error": "Génération lettre échouée"}


def main():
    try:
        raw = sys.stdin.read()
        input_data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"success": False, "error": "Invalid JSON input"}))
        sys.exit(1)

    action = input_data.get("action", "")

    try:
        if action == "cv":
            result = generate_cv(input_data)
        elif action == "cover-letter":
            result = generate_cover_letter(input_data)
        else:
            result = {"success": False, "error": f"Unknown action: {action}"}

        print(json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as e:
        logger.error("Generation failed: %s", e)
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

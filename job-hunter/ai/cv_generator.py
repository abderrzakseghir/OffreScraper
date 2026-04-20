"""
Générateur de CV LaTeX — Crée un .tex personnalisé par offre via l'API OpenAI.
Compile ensuite en PDF avec latexmk.
"""

import os
import subprocess
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
        raise ValueError("Clé API OpenAI manquante.")
    return key


def _read_cv_base(config: dict) -> str:
    cv_path = Path(__file__).resolve().parent.parent / config.get("latex", {}).get("cv_base", "latex/cv_base.tex")
    with open(cv_path, "r", encoding="utf-8") as f:
        return f.read()


def generate_cv_latex(offre_titre: str, offre_description: str, offre_entreprise: str,
                      score_data: dict | None = None, config: dict | None = None) -> str:
    """
    Génère un CV .tex personnalisé pour une offre spécifique.
    Retourne le contenu LaTeX généré.
    """
    import openai

    config = config or load_config()
    api_key = _get_api_key(config)
    model = config.get("openai", {}).get("model", "gpt-4o-mini")
    max_tokens = config.get("openai", {}).get("max_tokens", 4096)

    client = openai.OpenAI(api_key=api_key)
    cv_base = _read_cv_base(config)

    conseil = ""
    if score_data:
        comp = score_data.get('competences_matchees', [])
        if isinstance(comp, str):
            comp = [c.strip() for c in comp.split(",") if c.strip()]
        lac = score_data.get('lacunes', [])
        if isinstance(lac, str):
            lac = [l.strip() for l in lac.split(",") if l.strip()]
        conseil = f"""
Compétences matchées : {', '.join(comp)}
Lacunes identifiées : {', '.join(lac)}
Conseil : {score_data.get('conseil', '')}
"""

    prompt = f"""Tu es un expert en rédaction de CV techniques pour des développeurs.

Voici mon CV source en LaTeX :
```latex
{cv_base}
```

Voici l'offre d'emploi ciblée :
Titre : {offre_titre}
Entreprise : {offre_entreprise}
Description : {offre_description}

{conseil}

INSTRUCTIONS :
1. Adapte mon CV LaTeX pour maximiser mes chances pour cette offre spécifique
2. Réorganise les compétences pour mettre en avant celles demandées par l'offre
3. Reformule les descriptions d'expériences pour mettre en valeur les aspects pertinents
4. Garde le même format LaTeX et la même structure
5. Ne mens JAMAIS sur les compétences ou expériences — adapte uniquement la présentation
6. Le CV doit rester sur UNE page maximum
7. Réponds UNIQUEMENT avec le code LaTeX complet, sans commentaire ni explication

```latex
"""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        tex_content = response.choices[0].message.content.strip()
        # Nettoyer si wrapped dans des backticks
        if tex_content.startswith("```"):
            tex_content = tex_content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        
        logger.info("CV LaTeX généré pour '%s' (%d caractères)", offre_titre, len(tex_content))
        return tex_content
    except Exception as e:
        logger.error("Erreur génération CV pour '%s' : %s", offre_titre, e)
        return ""


def save_and_compile(tex_content: str, filename: str, config: dict | None = None) -> Path | None:
    """
    Sauvegarde le .tex et compile en PDF avec latexmk.
    Retourne le chemin du PDF si succès, None sinon.
    """
    config = config or load_config()
    output_dir = Path(__file__).resolve().parent.parent / config.get("latex", {}).get("output_dir", "latex/generated")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in filename)
    tex_path = output_dir / f"{safe_name}.tex"
    pdf_path = output_dir / f"{safe_name}.pdf"

    # Écrire le .tex
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex_content)
    logger.info("Fichier LaTeX sauvegardé : %s", tex_path)

    # Compiler en PDF
    compiler = config.get("latex", {}).get("compiler", "latexmk")
    try:
        result = subprocess.run(
            [compiler, "-pdf", "-interaction=nonstopmode", "-output-directory", str(output_dir), str(tex_path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(output_dir),
        )
        if pdf_path.exists():
            logger.info("PDF compilé : %s", pdf_path)
            # Nettoyage des fichiers auxiliaires
            for ext in [".aux", ".log", ".fls", ".fdb_latexmk", ".out", ".synctex.gz"]:
                aux_file = output_dir / f"{safe_name}{ext}"
                if aux_file.exists():
                    aux_file.unlink()
            return pdf_path
        else:
            logger.error("Compilation échouée : %s", result.stderr[:500])
            return None
    except FileNotFoundError:
        logger.error("Compilateur '%s' non trouvé. Installez TeX Live ou MiKTeX.", compiler)
        return None
    except subprocess.TimeoutExpired:
        logger.error("Compilation timeout pour %s", tex_path)
        return None


def generate_cv_for_offre(offre: dict, score_data: dict | None = None,
                          config: dict | None = None) -> dict:
    """Pipeline complet : génère le LaTeX puis compile le PDF."""
    tex = generate_cv_latex(
        offre_titre=offre.get("titre", ""),
        offre_description=offre.get("description", ""),
        offre_entreprise=offre.get("entreprise", ""),
        score_data=score_data,
        config=config,
    )

    if not tex:
        return {"success": False, "error": "Génération LaTeX échouée"}

    filename = f"CV_{offre.get('entreprise', 'unknown')}_{offre.get('titre', 'poste')}"
    pdf_path = save_and_compile(tex, filename, config)

    return {
        "success": pdf_path is not None,
        "tex": tex,
        "pdf_path": str(pdf_path) if pdf_path else None,
        "filename": filename,
    }

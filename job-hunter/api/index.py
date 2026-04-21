"""
Dashboard Flask — Interface web pour Vercel deployment.
Utilise Vercel Blob pour le stockage, token IA fourni par l'utilisateur.
"""

import sys
import os
import json
import uuid
import hashlib
import logging
import threading
import re
from functools import wraps
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, make_response

from db.blob_storage import (
    save_user_settings, get_user_settings,
    save_offre, get_offre, get_all_offres,
    save_score, get_score,
    save_cv, get_cv,
    save_lettre, get_lettre,
    update_offre_statut, get_stats,
    delete_offre, clear_all_offres,
)

logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent.parent / "dashboard" / "templates"))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "job-hunter-secret-key-change-me")

# ──────────────────── AUTH ────────────────────

CODES_FILE = Path(__file__).resolve().parent.parent / "codes.json"


def _load_codes() -> dict:
    """Load access codes from codes.json. Returns {code: label} dict."""
    try:
        if CODES_FILE.exists():
            with open(CODES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k.upper(): v for k, v in data.get("codes", {}).items()}
    except Exception:
        pass
    return {}


def _check_code(code: str) -> bool:
    return code.strip().upper() in _load_codes()


def _code_to_sid(code: str) -> str:
    """Derive a deterministic, stable session ID from an access code."""
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()[:32]


def require_auth(f):
    """Decorator: redirects to /login if user is not authenticated."""
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import session as flask_session
        if not flask_session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

# ──────────────────── SCRAPING STATE ────────────────────
# Per-session scraping state stored in memory
_scrape_states: dict[str, dict] = {}

def _get_scrape_state(sid: str) -> dict:
    return _scrape_states.get(sid, {
        "running": False,
        "progress": "",
        "inserted": 0,
        "errors": [],
        "started_at": None,
        "finished_at": None,
    })


def _apply_freshness_to_url(url: str, source_name: str, hours: int) -> str:
    """Adapte l'URL de la source pour filtrer par fraîcheur."""
    name_lower = source_name.lower()
    seconds = hours * 3600
    days = max(1, hours // 24)

    if "linkedin" in name_lower:
        if "f_TPR=" in url:
            url = re.sub(r"f_TPR=r\d+", f"f_TPR=r{seconds}", url)
        else:
            sep = "&" if "?" in url else "?"
            url += f"{sep}f_TPR=r{seconds}"
    elif "indeed" in name_lower:
        if "fromage=" in url:
            url = re.sub(r"fromage=\d+", f"fromage={days}", url)
        else:
            sep = "&" if "?" in url else "?"
            url += f"{sep}fromage={days}"
    # WTTJ n'a pas de filtre date dans l'URL
    return url


def _run_scrape_background(sid: str, params: dict):
    """Lance le scraper dans un thread background et sauvegarde les résultats."""
    import asyncio

    state = {
        "running": True,
        "progress": "Démarrage du scraping...",
        "inserted": 0,
        "errors": [],
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
    }
    _scrape_states[sid] = state

    try:
        import yaml
        from scraper.crawler import run_crawler_with_details

        settings = get_user_settings(sid)
        freshness_hours = int(params.get("freshness_hours", 168))
        sources_enabled = params.get("sources", ["LinkedIn", "Indeed", "Welcome to the Jungle"])

        # Charger la config de base pour les URLs sources
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            base_config = yaml.safe_load(f)

        filtered_sources = []
        for src in base_config.get("sources", []):
            if src["nom"] not in sources_enabled:
                continue
            modified_url = _apply_freshness_to_url(src["url"], src["nom"], freshness_hours)
            filtered_sources.append({**src, "actif": True, "url": modified_url})

        if not filtered_sources:
            state["progress"] = "Aucune source sélectionnée."
            state["running"] = False
            state["finished_at"] = datetime.now().isoformat()
            return

        run_config = {
            **base_config,
            "sources": filtered_sources,
        }
        # Override keywords from user settings if set
        keywords = [k.strip() for k in settings.get("keywords", "").split(",") if k.strip()]
        if keywords:
            run_config.setdefault("recherche", {})["mots_cles"] = keywords

        state["progress"] = f"Scraping {len(filtered_sources)} source(s) — fraîcheur : {freshness_hours}h..."

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            _, enriched_offres = loop.run_until_complete(run_crawler_with_details(run_config))
        finally:
            loop.close()

        state["progress"] = f"Sauvegarde de {len(enriched_offres)} offre(s)..."
        inserted = 0
        for offre in enriched_offres:
            try:
                save_offre(sid, offre)
                inserted += 1
            except Exception as e:
                state["errors"].append(str(e))

        state["inserted"] = inserted
        state["progress"] = f"✅ Terminé ! {inserted} offre(s) ajoutée(s)."

        # Sauvegarder la date du dernier scraping dans les settings
        settings["last_scrape"] = datetime.now().isoformat()
        settings["last_scrape_params"] = params
        save_user_settings(sid, settings)

    except Exception as e:
        logger.exception("Scraping error")
        state["progress"] = f"❌ Erreur : {e}"
        state["errors"].append(str(e))
    finally:
        state["running"] = False
        state["finished_at"] = datetime.now().isoformat()
        _scrape_states[sid] = state


def _get_session_id():
    """Get the blob storage session ID. When authenticated, derived from access code."""
    from flask import session as flask_session
    if flask_session.get("authenticated") and flask_session.get("jh_sid"):
        return flask_session["jh_sid"]
    # Fallback for unauthenticated context (e.g. tests)
    sid = request.cookies.get("jh_session")
    if not sid:
        sid = uuid.uuid4().hex
    return sid


def _set_session_cookie(response, sid):
    response.set_cookie("jh_session", sid, max_age=365 * 24 * 3600, httponly=True, samesite="Lax")
    return response


def _build_config_from_settings(settings: dict) -> dict:
    """Build a config dict compatible with existing AI modules from user settings."""
    return {
        "openai": {
            "api_key": settings.get("api_key", ""),
            "model": settings.get("model", "gpt-4o-mini"),
            "max_tokens": 4096,
        },
        "profil": {
            "nom": settings.get("nom", ""),
            "titre": settings.get("titre", ""),
            "statut": settings.get("statut", ""),
            "objectif": settings.get("objectif", ""),
            "description": settings.get("description", ""),
            "competences": [c.strip() for c in settings.get("competences", "").split(",") if c.strip()],
            "experience": settings.get("experience", []),
            "formation": settings.get("formation", []),
            "portfolio": settings.get("portfolio", ""),
            "linkedin": settings.get("linkedin", ""),
            "chef_nom": settings.get("chef_nom", ""),
            "chef_email": settings.get("chef_email", ""),
        },
        "recherche": {
            "mots_cles": [k.strip() for k in settings.get("keywords", "").split(",") if k.strip()],
        },
        "ia_instructions": settings.get("ia_instructions", ""),
        "latex": {
            "cv_base": str(Path(__file__).resolve().parent.parent / "latex" / "cv_base.tex"),
        },
    }


# ──────────────────── AUTH ROUTES ────────────────────


@app.route("/login", methods=["GET", "POST"])
def login():
    from flask import session as flask_session
    if flask_session.get("authenticated"):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if _check_code(code):
            flask_session.clear()
            flask_session["authenticated"] = True
            flask_session["code"] = code.strip().upper()
            flask_session["jh_sid"] = _code_to_sid(code)
            flask_session.permanent = True
            next_url = request.args.get("next") or url_for("index")
            # Only allow relative redirects to prevent open redirect
            if not next_url.startswith("/"):
                next_url = url_for("index")
            return redirect(next_url)
        else:
            error = "Code d'accès invalide. Vérifiez le code et réessayez."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    from flask import session as flask_session
    flask_session.clear()
    resp = make_response(redirect(url_for("login")))
    resp.delete_cookie("jh_session")
    return resp


# ──────────────────── CODES MANAGEMENT ────────────────────

def _save_codes(codes: dict):
    """Persist codes dict to codes.json."""
    with open(CODES_FILE, "w", encoding="utf-8") as f:
        json.dump({"codes": codes}, f, ensure_ascii=False, indent=2)


@app.route("/codes")
@require_auth
def codes_page():
    codes = _load_codes()
    message = request.args.get("msg", "")
    message_type = request.args.get("type", "success")
    return render_template("codes.html", codes=codes, message=message, message_type=message_type)


@app.route("/codes/add", methods=["POST"])
@require_auth
def codes_add():
    code = request.form.get("code", "").strip().upper()
    label = request.form.get("label", "").strip() or code

    if not code:
        return redirect(url_for("codes_page") + "?msg=Code+vide.&type=error")

    # Basic validation: only alphanumeric + dash/underscore
    if not re.match(r'^[A-Z0-9_\-]{2,32}$', code):
        return redirect(url_for("codes_page") + "?msg=Code+invalide.+Utilisez+uniquement+des+lettres,+chiffres,+tirets.&type=error")

    codes = _load_codes()
    if code in codes:
        return redirect(url_for("codes_page") + f"?msg=Le+code+{code}+existe+d%C3%A9j%C3%A0.&type=error")

    codes[code] = label
    _save_codes(codes)
    return redirect(url_for("codes_page") + f"?msg=Code+{code}+ajout%C3%A9+avec+succ%C3%A8s.&type=success")


@app.route("/codes/delete", methods=["POST"])
@require_auth
def codes_delete():
    code = request.form.get("code", "").strip().upper()
    codes = _load_codes()

    if code not in codes:
        return redirect(url_for("codes_page") + "?msg=Code+introuvable.&type=error")

    del codes[code]
    _save_codes(codes)
    return redirect(url_for("codes_page") + f"?msg=Code+{code}+supprim%C3%A9.&type=success")


# ──────────────────── PAGES ────────────────────


@app.route("/")
@require_auth
def index():
    sid = _get_session_id()
    offres = get_all_offres(sid)
    stats = get_stats(sid)

    filtre_source = request.args.get("source", "")
    filtre_statut = request.args.get("statut", "")
    filtre_score_min = request.args.get("score_min", "")
    filtre_search = request.args.get("q", "")

    if filtre_source:
        offres = [o for o in offres if o.get("source", "").lower() == filtre_source.lower()]
    if filtre_statut:
        offres = [o for o in offres if o.get("statut", "") == filtre_statut]
    if filtre_score_min:
        try:
            smin = int(filtre_score_min)
            offres = [o for o in offres if (o.get("score") or 0) >= smin]
        except ValueError:
            pass
    if filtre_search:
        q = filtre_search.lower()
        offres = [o for o in offres if q in (o.get("titre", "") + " " + o.get("entreprise", "")).lower()]

    sources = sorted(set(o.get("source", "") for o in get_all_offres(sid) if o.get("source")))
    settings = get_user_settings(sid)

    resp = make_response(render_template("index.html",
        offres=offres, stats=stats, sources=sources,
        filtre_source=filtre_source, filtre_statut=filtre_statut,
        filtre_score_min=filtre_score_min, filtre_search=filtre_search,
        has_settings=bool(settings.get("api_key")),
        last_scrape=settings.get("last_scrape", ""),
        last_scrape_params=settings.get("last_scrape_params", {}),
        scrape_state=_get_scrape_state(sid),
    ))
    return _set_session_cookie(resp, sid)


@app.route("/settings", methods=["GET", "POST"])
@require_auth
def settings_page():
    sid = _get_session_id()

    if request.method == "POST":
        settings = {
            "api_key": request.form.get("api_key", "").strip(),
            "model": request.form.get("model", "gpt-4o-mini").strip(),
            "nom": request.form.get("nom", "").strip(),
            "titre": request.form.get("titre", "").strip(),
            "statut": request.form.get("statut", "").strip(),
            "objectif": request.form.get("objectif", "").strip(),
            "description": request.form.get("description", "").strip(),
            "competences": request.form.get("competences", "").strip(),
            "keywords": request.form.get("keywords", "").strip(),
            "ia_instructions": request.form.get("ia_instructions", "").strip(),
            "portfolio": request.form.get("portfolio", "").strip(),
            "linkedin": request.form.get("linkedin", "").strip(),
            "chef_nom": request.form.get("chef_nom", "").strip(),
            "chef_email": request.form.get("chef_email", "").strip(),
            "experience_json": request.form.get("experience_json", "[]").strip(),
            "formation_json": request.form.get("formation_json", "[]").strip(),
        }
        # Parse experience/formation JSON
        try:
            settings["experience"] = json.loads(settings.pop("experience_json"))
        except (json.JSONDecodeError, KeyError):
            settings["experience"] = []
        try:
            settings["formation"] = json.loads(settings.pop("formation_json"))
        except (json.JSONDecodeError, KeyError):
            settings["formation"] = []

        save_user_settings(sid, settings)
        resp = make_response(redirect(url_for("settings_page") + "?saved=1"))
        return _set_session_cookie(resp, sid)

    settings = get_user_settings(sid)
    resp = make_response(render_template("settings.html", settings=settings))
    return _set_session_cookie(resp, sid)


@app.route("/offre/<offre_id>")
@require_auth
def offre_detail(offre_id: str):
    sid = _get_session_id()
    offre = get_offre(sid, offre_id)
    if not offre:
        return "Offre non trouvée", 404

    score_data = get_score(sid, offre_id)
    cv_data = get_cv(sid, offre_id)
    lettre_data = get_lettre(sid, offre_id)
    stats = get_stats(sid)
    settings = get_user_settings(sid)

    resp = make_response(render_template("detail.html",
        offre=offre, score=score_data, cv=cv_data, lettre=lettre_data,
        stats=stats, has_api_key=bool(settings.get("api_key")),
    ))
    return _set_session_cookie(resp, sid)


# ──────────────────── API ROUTES ────────────────────


@app.route("/api/offre/<offre_id>/statut", methods=["POST"])
@require_auth
def api_update_statut(offre_id: str):
    sid = _get_session_id()
    data = request.get_json()
    statut = data.get("statut", "")
    valid = ("nouveau", "vu", "postulé", "refusé", "entretien")
    if statut not in valid:
        return jsonify({"error": f"Statut invalide. Valides: {valid}"}), 400
    update_offre_statut(sid, offre_id, statut)
    return jsonify({"success": True})


@app.route("/api/offre/<offre_id>/screen", methods=["POST"])
@require_auth
def api_screen_offre(offre_id: str):
    """Run AI screening (matching) on a single offer."""
    sid = _get_session_id()
    settings = get_user_settings(sid)

    if not settings.get("api_key"):
        return jsonify({"error": "Veuillez configurer votre clé API dans les paramètres."}), 400

    offre = get_offre(sid, offre_id)
    if not offre:
        return jsonify({"error": "Offre non trouvée."}), 404

    config = _build_config_from_settings(settings)

    # Add custom IA instructions to the config
    ia_instructions = settings.get("ia_instructions", "")

    try:
        from ai.matcher import score_offre, _build_profil_prompt
        import openai

        api_key = config["openai"]["api_key"]
        model = config["openai"].get("model", "gpt-4o-mini")
        client = openai.OpenAI(api_key=api_key)

        profil_prompt = _build_profil_prompt(config)

        extra = ""
        if ia_instructions:
            extra = f"\n\nINSTRUCTIONS SUPPLÉMENTAIRES DU CANDIDAT :\n{ia_instructions}"

        prompt = f"""Tu es un expert en recrutement IT. Analyse la correspondance entre le profil candidat et l'offre d'emploi.

{profil_prompt}

OFFRE D'EMPLOI :
Titre : {offre.get('titre', '')}
Entreprise : {offre.get('entreprise', '')}
Description : {offre.get('description', '')}
{extra}

Réponds UNIQUEMENT au format JSON suivant (pas de markdown, pas de commentaires) :
{{
    "score": <entier de 0 à 100>,
    "justification": "<explication courte de 2-3 phrases>",
    "competences_matchees": ["comp1", "comp2"],
    "lacunes": ["lacune1", "lacune2"],
    "conseil": "<conseil pour personnaliser la candidature>"
}}"""

        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)

        # Normalize lists to strings for storage
        if isinstance(result.get("competences_matchees"), list):
            result["competences_matchees"] = ", ".join(result["competences_matchees"])
        if isinstance(result.get("lacunes"), list):
            result["lacunes"] = ", ".join(result["lacunes"])

        save_score(sid, offre_id, result)
        return jsonify({"success": True, "score": result})

    except Exception as e:
        logger.exception("Screening error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/offre/<offre_id>/generate-cv", methods=["POST"])
@require_auth
def api_generate_cv(offre_id: str):
    """Generate a personalized CV LaTeX for an offer."""
    sid = _get_session_id()
    settings = get_user_settings(sid)

    if not settings.get("api_key"):
        return jsonify({"error": "Veuillez configurer votre clé API dans les paramètres."}), 400

    offre = get_offre(sid, offre_id)
    if not offre:
        return jsonify({"error": "Offre non trouvée."}), 404

    config = _build_config_from_settings(settings)
    score_data = get_score(sid, offre_id)

    try:
        from ai.cv_generator import generate_cv_latex, _read_cv_base
        import openai

        api_key = config["openai"]["api_key"]
        model = config["openai"].get("model", "gpt-4o-mini")
        client = openai.OpenAI(api_key=api_key)

        # Read CV base
        cv_base_path = Path(__file__).resolve().parent.parent / "latex" / "cv_base.tex"
        with open(cv_base_path, "r", encoding="utf-8") as f:
            cv_base = f.read()

        conseil = ""
        if score_data:
            comp = score_data.get("competences_matchees", "")
            if isinstance(comp, list):
                comp = ", ".join(comp)
            lac = score_data.get("lacunes", "")
            if isinstance(lac, list):
                lac = ", ".join(lac)
            conseil = f"\nCompétences matchées : {comp}\nLacunes : {lac}\nConseil : {score_data.get('conseil', '')}"

        ia_instructions = settings.get("ia_instructions", "")
        extra = f"\n\nINSTRUCTIONS SUPPLÉMENTAIRES DU CANDIDAT :\n{ia_instructions}" if ia_instructions else ""

        # Add portfolio/linkedin to CV if provided
        portfolio_info = ""
        if settings.get("portfolio"):
            portfolio_info += f"\nLe candidat a un portfolio : {settings['portfolio']}"
        if settings.get("linkedin"):
            portfolio_info += f"\nProfil LinkedIn : {settings['linkedin']}"

        prompt = f"""Tu es un expert en rédaction de CV techniques pour des développeurs.

Voici mon CV source en LaTeX :
```latex
{cv_base}
```

Voici l'offre d'emploi ciblée :
Titre : {offre.get('titre', '')}
Entreprise : {offre.get('entreprise', '')}
Description : {offre.get('description', '')}

{conseil}
{portfolio_info}
{extra}

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

        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        tex_content = response.choices[0].message.content.strip()
        if tex_content.startswith("```"):
            tex_content = tex_content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        cv_result = {"tex": tex_content}
        save_cv(sid, offre_id, cv_result)
        return jsonify({"success": True, "tex": tex_content})

    except Exception as e:
        logger.exception("CV generation error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/offre/<offre_id>/generate-lettre", methods=["POST"])
@require_auth
def api_generate_lettre(offre_id: str):
    """Generate a personalized cover letter LaTeX for an offer."""
    sid = _get_session_id()
    settings = get_user_settings(sid)

    if not settings.get("api_key"):
        return jsonify({"error": "Veuillez configurer votre clé API dans les paramètres."}), 400

    offre = get_offre(sid, offre_id)
    if not offre:
        return jsonify({"error": "Offre non trouvée."}), 404

    config = _build_config_from_settings(settings)
    score_data = get_score(sid, offre_id)

    try:
        import openai

        api_key = config["openai"]["api_key"]
        model = config["openai"].get("model", "gpt-4o-mini")
        client = openai.OpenAI(api_key=api_key)

        profil = config["profil"]
        competences = ", ".join(profil.get("competences", []))
        experiences = ""
        for exp in profil.get("experience", []):
            experiences += f"- {exp.get('poste', '')} chez {exp.get('entreprise', '')} ({exp.get('periode', '')})\n"

        conseil = ""
        if score_data:
            comp = score_data.get("competences_matchees", "")
            conseil = f"Compétences matchées : {comp}"

        ia_instructions = settings.get("ia_instructions", "")
        extra = f"\n\nINSTRUCTIONS SUPPLÉMENTAIRES DU CANDIDAT :\n{ia_instructions}" if ia_instructions else ""

        # Reference contact
        ref_contact = ""
        if settings.get("chef_nom") and settings.get("chef_email"):
            ref_contact = f"""
Le candidat souhaite inclure une référence professionnelle dans la lettre :
- Nom du référent : {settings['chef_nom']}
- Email du référent : {settings['chef_email']}
Ajoute une mention de cette référence à la fin de la lettre (ex: "Pour toute référence, vous pouvez contacter...")
"""

        prompt = f"""Tu es un expert en rédaction de lettres de motivation pour des développeurs.

Profil du candidat :
Nom : {profil.get('nom', '')}
Titre : {profil.get('titre', '')}
Statut : {profil.get('statut', '')}
Compétences : {competences}

Expérience :
{experiences}

OFFRE D'EMPLOI :
Titre : {offre.get('titre', '')}
Entreprise : {offre.get('entreprise', '')}
Description : {offre.get('description', '')}

{conseil}
{ref_contact}
{extra}

INSTRUCTIONS :
1. Génère une lettre de motivation en format LaTeX (template professionnel)
2. Mets en avant les compétences et expériences pertinentes pour cette offre
3. Montre la motivation et la connaissance de l'entreprise
4. Reste concis (une page maximum)
5. Ne mens JAMAIS — adapte uniquement la présentation
6. Ton professionnel mais pas trop formel
7. Utilise le package lettre ou un format classique LaTeX
8. Réponds UNIQUEMENT avec le code LaTeX complet

```latex
"""

        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        tex_content = response.choices[0].message.content.strip()
        if tex_content.startswith("```"):
            tex_content = tex_content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        lettre_result = {"tex": tex_content}
        save_lettre(sid, offre_id, lettre_result)
        return jsonify({"success": True, "tex": tex_content})

    except Exception as e:
        logger.exception("Lettre generation error")
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats")
@require_auth
def api_stats():
    sid = _get_session_id()
    return jsonify(get_stats(sid))


@app.route("/api/import-sqlite", methods=["POST"])
@require_auth
def api_import_sqlite():
    """Import offres from local SQLite database into blob storage."""
    sid = _get_session_id()
    try:
        from db.database import get_offres_with_scores, get_score_for_offre, get_cv_for_offre, init_db
        init_db()
        offres = get_offres_with_scores(limit=500)
        imported = 0
        for o in offres:
            offre_data = {
                "id": str(o.get("id", "")),
                "titre": o.get("titre", ""),
                "entreprise": o.get("entreprise", ""),
                "localisation": o.get("localisation", ""),
                "description": o.get("description", ""),
                "url": o.get("url", ""),
                "source": o.get("source", ""),
                "type_contrat": o.get("type_contrat", "CDI"),
                "date_publication": o.get("date_publication", ""),
                "technologies": o.get("technologies", ""),
                "statut": o.get("statut", "nouveau"),
            }
            oid = save_offre(sid, offre_data)

            # Import score if exists
            score = get_score_for_offre(o["id"])
            if score:
                save_score(sid, oid, dict(score))

            # Import CV if exists
            cv = get_cv_for_offre(o["id"])
            if cv and cv.get("tex_content"):
                save_cv(sid, oid, {"tex": cv["tex_content"]})

            imported += 1

        resp = make_response(jsonify({"success": True, "imported": imported}))
        return _set_session_cookie(resp, sid)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/offre/<offre_id>/delete", methods=["POST"])
@require_auth
def api_delete_offre(offre_id: str):
    sid = _get_session_id()
    delete_offre(sid, offre_id)
    resp = make_response(jsonify({"success": True}))
    return _set_session_cookie(resp, sid)


@app.route("/api/storage/clear", methods=["POST"])
@require_auth
def api_clear_storage():
    sid = _get_session_id()
    clear_all_offres(sid)
    resp = make_response(jsonify({"success": True}))
    return _set_session_cookie(resp, sid)


@app.route("/api/scrape", methods=["POST"])
@require_auth
def api_scrape():
    sid = _get_session_id()
    data = request.get_json() or {}

    # Save schedule only (no actual scraping)
    if data.get("save_schedule_only"):
        settings = get_user_settings(sid)
        settings.setdefault("last_scrape_params", {})["schedule_hours"] = int(data.get("schedule_hours", 0))
        save_user_settings(sid, settings)
        resp = make_response(jsonify({"success": True}))
        return _set_session_cookie(resp, sid)

    state = _get_scrape_state(sid)
    if state.get("running"):
        return jsonify({"error": "Scraping déjà en cours."}), 400

    params = {
        "freshness_hours": int(data.get("freshness_hours", 168)),
        "sources": data.get("sources", ["LinkedIn", "Indeed", "Welcome to the Jungle"]),
    }

    t = threading.Thread(target=_run_scrape_background, args=(sid, params), daemon=True)
    t.start()

    resp = make_response(jsonify({"success": True, "message": "Scraping lancé en arrière-plan."}))
    return _set_session_cookie(resp, sid)


@app.route("/api/scrape/status")
@require_auth
def api_scrape_status():
    sid = _get_session_id()
    state = _get_scrape_state(sid)
    resp = make_response(jsonify(state))
    return _set_session_cookie(resp, sid)


# ──────────────────── VERCEL ENTRY ────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)

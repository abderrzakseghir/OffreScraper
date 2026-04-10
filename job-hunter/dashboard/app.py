"""
Dashboard Flask — Interface web pour visualiser les offres, scores et CVs.
"""

import sys
import os
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Charger .env si présent
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

from flask import Flask, render_template, send_file, jsonify, request, redirect, url_for
from db.database import (
    get_offres_with_scores,
    get_offre_by_id,
    get_score_for_offre,
    get_cv_for_offre,
    get_stats,
    get_offres,
    update_offre_statut,
    init_db,
)

app = Flask(__name__)


@app.route("/")
def index():
    stats = get_stats()
    offres = get_offres_with_scores(limit=200)

    # Filtrage côté serveur
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

    # Sources distinctes pour le filtre
    all_offres = get_offres_with_scores(limit=200)
    sources = sorted(set(o.get("source", "") for o in all_offres if o.get("source")))

    return render_template("index.html", offres=offres, stats=stats, sources=sources,
                           filtre_source=filtre_source, filtre_statut=filtre_statut,
                           filtre_score_min=filtre_score_min, filtre_search=filtre_search)


@app.route("/offre/<int:offre_id>")
def offre_detail(offre_id: int):
    offre = get_offre_by_id(offre_id)
    if not offre:
        return "Offre non trouvée", 404
    score = get_score_for_offre(offre_id)
    cv = get_cv_for_offre(offre_id)
    stats = get_stats()
    return render_template("detail.html", offre=offre, score=score, cv=cv, stats=stats)


@app.route("/cv/<int:offre_id>")
def download_cv(offre_id: int):
    cv = get_cv_for_offre(offre_id)
    if not cv or not cv.get("pdf_path"):
        return "CV non trouvé", 404
    pdf_path = Path(cv["pdf_path"])
    if not pdf_path.exists():
        return "Fichier PDF non trouvé", 404
    return send_file(pdf_path, as_attachment=True, download_name=f"{cv.get('filename', 'cv')}.pdf")


@app.route("/api/offres")
def api_offres():
    offres = get_offres_with_scores(limit=200)
    return jsonify(offres)


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/offre/<int:offre_id>/statut", methods=["POST"])
def api_update_statut(offre_id: int):
    data = request.get_json()
    statut = data.get("statut", "")
    valid_statuts = ("nouveau", "vu", "postulé", "refusé", "entretien")
    if statut not in valid_statuts:
        return jsonify({"error": f"Statut invalide. Valides: {valid_statuts}"}), 400
    update_offre_statut(offre_id, statut)
    return jsonify({"success": True})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)

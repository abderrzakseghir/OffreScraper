"""
Vercel Blob Storage — Remplace SQLite pour le déploiement serverless.
Stocke les données en JSON dans Vercel Blob.
"""

import json
import os
import logging
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import vercel_blob, fallback to local file storage for dev
try:
    from vercel_blob import put, list as blob_list, head, delete
    VERCEL_BLOB_AVAILABLE = True
except ImportError:
    VERCEL_BLOB_AVAILABLE = False

LOCAL_STORAGE_DIR = (
    "/tmp/_local_blob"
    if os.environ.get("VERCEL")
    else os.path.join(os.path.dirname(__file__), "..", "_local_blob")
)


def _ensure_local_dir():
    os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)


def _blob_token():
    return os.environ.get("BLOB_READ_WRITE_TOKEN", "")


def blob_put(path: str, data: str) -> str:
    """Store data in Vercel Blob or local filesystem."""
    if VERCEL_BLOB_AVAILABLE and _blob_token():
        result = put(path, data.encode("utf-8"), {
            "access": "public",
            "token": _blob_token(),
            "addRandomSuffix": False,
        })
        return result.get("url", path)
    else:
        _ensure_local_dir()
        safe_path = path.replace("/", "_")
        filepath = os.path.join(LOCAL_STORAGE_DIR, safe_path)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(data)
        return filepath


def blob_get(path: str) -> str | None:
    """Get data from Vercel Blob or local filesystem."""
    if VERCEL_BLOB_AVAILABLE and _blob_token():
        import urllib.request
        try:
            blobs = blob_list({"prefix": path, "token": _blob_token()})
            if blobs.get("blobs"):
                url = blobs["blobs"][0]["url"]
                with urllib.request.urlopen(url) as resp:
                    return resp.read().decode("utf-8")
        except Exception as e:
            logger.debug("Blob get error: %s", e)
        return None
    else:
        _ensure_local_dir()
        safe_path = path.replace("/", "_")
        filepath = os.path.join(LOCAL_STORAGE_DIR, safe_path)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        return None


def blob_delete(path: str):
    """Delete from Vercel Blob or local."""
    if VERCEL_BLOB_AVAILABLE and _blob_token():
        try:
            blobs = blob_list({"prefix": path, "token": _blob_token()})
            for b in blobs.get("blobs", []):
                delete(b["url"], {"token": _blob_token()})
        except Exception:
            pass
    else:
        _ensure_local_dir()
        safe_path = path.replace("/", "_")
        filepath = os.path.join(LOCAL_STORAGE_DIR, safe_path)
        if os.path.exists(filepath):
            os.remove(filepath)


def blob_list_prefix(prefix: str) -> list[str]:
    """List blob keys with a prefix."""
    if VERCEL_BLOB_AVAILABLE and _blob_token():
        try:
            result = blob_list({"prefix": prefix, "token": _blob_token()})
            return [b["pathname"] for b in result.get("blobs", [])]
        except Exception:
            return []
    else:
        _ensure_local_dir()
        safe_prefix = prefix.replace("/", "_")
        files = []
        for f in os.listdir(LOCAL_STORAGE_DIR):
            if f.startswith(safe_prefix):
                files.append(f.replace("_", "/", f.count("_")))
        return files


# ──────────────────── HIGH-LEVEL DATA OPS ────────────────────

def _user_key(session_id: str) -> str:
    """Generate a storage prefix per user session."""
    return f"users/{session_id}"


def save_user_settings(session_id: str, settings: dict):
    """Save user settings (API key, profile, keywords, etc.)."""
    key = f"{_user_key(session_id)}/settings.json"
    blob_put(key, json.dumps(settings, ensure_ascii=False))


def get_user_settings(session_id: str) -> dict:
    """Get user settings."""
    key = f"{_user_key(session_id)}/settings.json"
    data = blob_get(key)
    if data:
        return json.loads(data)
    return {}


def save_offre(session_id: str, offre: dict) -> str:
    """Save an offre. Returns the offre ID."""
    offre_id = offre.get("id") or hashlib.md5(
        (offre.get("url", "") or offre.get("titre", "") + offre.get("entreprise", "")).encode()
    ).hexdigest()[:12]
    offre["id"] = offre_id
    offre.setdefault("date_ajout", datetime.now().isoformat())
    offre.setdefault("statut", "nouveau")

    key = f"{_user_key(session_id)}/offres/{offre_id}.json"
    blob_put(key, json.dumps(offre, ensure_ascii=False))

    # Update index
    _update_offre_index(session_id, offre_id, {
        "id": offre_id,
        "titre": offre.get("titre", ""),
        "entreprise": offre.get("entreprise", ""),
        "localisation": offre.get("localisation", ""),
        "source": offre.get("source", ""),
        "statut": offre.get("statut", "nouveau"),
        "date_ajout": offre.get("date_ajout", ""),
        "url": offre.get("url", ""),
    })
    return offre_id


def _update_offre_index(session_id: str, offre_id: str, summary: dict):
    key = f"{_user_key(session_id)}/offres_index.json"
    data = blob_get(key)
    index = json.loads(data) if data else {}
    index[offre_id] = summary
    blob_put(key, json.dumps(index, ensure_ascii=False))


def get_offre(session_id: str, offre_id: str) -> dict | None:
    key = f"{_user_key(session_id)}/offres/{offre_id}.json"
    data = blob_get(key)
    return json.loads(data) if data else None


def get_all_offres(session_id: str) -> list[dict]:
    key = f"{_user_key(session_id)}/offres_index.json"
    data = blob_get(key)
    if not data:
        return []
    index = json.loads(data)

    # Enrich with scores
    scores_key = f"{_user_key(session_id)}/scores_index.json"
    scores_data = blob_get(scores_key)
    scores_index = json.loads(scores_data) if scores_data else {}

    result = []
    for offre_id, summary in index.items():
        entry = dict(summary)
        if offre_id in scores_index:
            entry["score"] = scores_index[offre_id].get("score")
        else:
            entry["score"] = None
        result.append(entry)

    result.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return result


def save_score(session_id: str, offre_id: str, score_data: dict):
    key = f"{_user_key(session_id)}/scores/{offre_id}.json"
    score_data["date_calcul"] = datetime.now().isoformat()
    blob_put(key, json.dumps(score_data, ensure_ascii=False))

    # Update scores index
    idx_key = f"{_user_key(session_id)}/scores_index.json"
    data = blob_get(idx_key)
    index = json.loads(data) if data else {}
    index[offre_id] = {"score": score_data.get("score", 0)}
    blob_put(idx_key, json.dumps(index, ensure_ascii=False))


def get_score(session_id: str, offre_id: str) -> dict | None:
    key = f"{_user_key(session_id)}/scores/{offre_id}.json"
    data = blob_get(key)
    return json.loads(data) if data else None


def save_cv(session_id: str, offre_id: str, cv_data: dict):
    key = f"{_user_key(session_id)}/cvs/{offre_id}.json"
    cv_data["date_generation"] = datetime.now().isoformat()
    blob_put(key, json.dumps(cv_data, ensure_ascii=False))


def get_cv(session_id: str, offre_id: str) -> dict | None:
    key = f"{_user_key(session_id)}/cvs/{offre_id}.json"
    data = blob_get(key)
    return json.loads(data) if data else None


def save_lettre(session_id: str, offre_id: str, lettre_data: dict):
    key = f"{_user_key(session_id)}/lettres/{offre_id}.json"
    lettre_data["date_generation"] = datetime.now().isoformat()
    blob_put(key, json.dumps(lettre_data, ensure_ascii=False))


def get_lettre(session_id: str, offre_id: str) -> dict | None:
    key = f"{_user_key(session_id)}/lettres/{offre_id}.json"
    data = blob_get(key)
    return json.loads(data) if data else None


def update_offre_statut(session_id: str, offre_id: str, statut: str):
    offre = get_offre(session_id, offre_id)
    if offre:
        offre["statut"] = statut
        save_offre(session_id, offre)


def delete_offre(session_id: str, offre_id: str):
    """Delete an offre and all its associated data (score, cv, lettre)."""
    for sub in ("offres", "scores", "cvs", "lettres"):
        blob_delete(f"{_user_key(session_id)}/{sub}/{offre_id}.json")

    # Remove from offres index
    idx_key = f"{_user_key(session_id)}/offres_index.json"
    data = blob_get(idx_key)
    if data:
        index = json.loads(data)
        index.pop(offre_id, None)
        blob_put(idx_key, json.dumps(index, ensure_ascii=False))

    # Remove from scores index
    sidx_key = f"{_user_key(session_id)}/scores_index.json"
    sdata = blob_get(sidx_key)
    if sdata:
        sindex = json.loads(sdata)
        sindex.pop(offre_id, None)
        blob_put(sidx_key, json.dumps(sindex, ensure_ascii=False))


def clear_all_offres(session_id: str):
    """Delete all offres, scores, CVs and lettres for a session (keeps settings)."""
    prefix = _user_key(session_id)

    if VERCEL_BLOB_AVAILABLE and _blob_token():
        try:
            blobs = blob_list({"prefix": prefix + "/offres", "token": _blob_token()})
            for b in blobs.get("blobs", []):
                delete(b["url"], {"token": _blob_token()})
            for sub in ("scores", "cvs", "lettres", "offres_index.json", "scores_index.json"):
                blobs2 = blob_list({"prefix": f"{prefix}/{sub}", "token": _blob_token()})
                for b in blobs2.get("blobs", []):
                    delete(b["url"], {"token": _blob_token()})
        except Exception:
            pass
    else:
        _ensure_local_dir()
        safe_prefix = prefix.replace("/", "_")
        for fname in list(os.listdir(LOCAL_STORAGE_DIR)):
            if fname.startswith(safe_prefix) and "settings" not in fname:
                os.remove(os.path.join(LOCAL_STORAGE_DIR, fname))


def get_stats(session_id: str) -> dict:
    offres = get_all_offres(session_id)
    scores_key = f"{_user_key(session_id)}/scores_index.json"
    scores_data = blob_get(scores_key)
    scores_index = json.loads(scores_data) if scores_data else {}

    total = len(offres)
    scored = len(scores_index)
    scores_vals = [v.get("score", 0) for v in scores_index.values()]
    avg = round(sum(scores_vals) / len(scores_vals), 1) if scores_vals else 0

    return {
        "total_offres": total,
        "offres_scorees": scored,
        "cvs_generes": 0,
        "score_moyen": avg,
    }

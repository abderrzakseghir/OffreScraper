"""
Base de données SQLite — Modèles Offre, CV, Score.
Zéro configuration, migrable vers PostgreSQL si besoin.
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent / "job_hunter.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS offres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titre TEXT NOT NULL,
    entreprise TEXT DEFAULT '',
    localisation TEXT DEFAULT '',
    description TEXT DEFAULT '',
    url TEXT UNIQUE,
    source TEXT DEFAULT '',
    type_contrat TEXT DEFAULT 'CDI',
    date_publication TEXT DEFAULT '',
    technologies TEXT DEFAULT '',
    date_ajout TEXT NOT NULL,
    statut TEXT DEFAULT 'nouveau'
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offre_id INTEGER NOT NULL,
    score INTEGER DEFAULT 0,
    justification TEXT DEFAULT '',
    competences_matchees TEXT DEFAULT '',
    lacunes TEXT DEFAULT '',
    conseil TEXT DEFAULT '',
    date_calcul TEXT NOT NULL,
    FOREIGN KEY (offre_id) REFERENCES offres(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cvs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offre_id INTEGER NOT NULL,
    tex_content TEXT DEFAULT '',
    pdf_path TEXT DEFAULT '',
    filename TEXT DEFAULT '',
    date_generation TEXT NOT NULL,
    FOREIGN KEY (offre_id) REFERENCES offres(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_offres_url ON offres(url);
CREATE INDEX IF NOT EXISTS idx_offres_statut ON offres(statut);
CREATE INDEX IF NOT EXISTS idx_scores_offre ON scores(offre_id);
CREATE INDEX IF NOT EXISTS idx_cvs_offre ON cvs(offre_id);
"""


@contextmanager
def get_db(db_path: str | None = None):
    """Context manager pour obtenir une connexion DB."""
    path = db_path or str(DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | None = None):
    """Initialise la base de données avec le schéma."""
    with get_db(db_path) as conn:
        conn.executescript(SCHEMA)
    logger.info("Base de données initialisée : %s", db_path or DB_PATH)


# ──────────────────────── OFFRES ────────────────────────

def insert_offre(offre: dict, db_path: str | None = None) -> int | None:
    """Insère une offre. Retourne l'ID ou None si doublon (même URL)."""
    with get_db(db_path) as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO offres (titre, entreprise, localisation, description,
                   url, source, type_contrat, date_publication, technologies, date_ajout, statut)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    offre.get("titre", ""),
                    offre.get("entreprise", ""),
                    offre.get("localisation", ""),
                    offre.get("description", ""),
                    offre.get("url", ""),
                    offre.get("source", ""),
                    offre.get("type_contrat", "CDI"),
                    offre.get("date_publication", ""),
                    ",".join(offre.get("technologies", [])),
                    datetime.now().isoformat(),
                    "nouveau",
                ),
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            logger.debug("Offre déjà existante : %s", offre.get("url", ""))
            return None


def get_offres(statut: str | None = None, limit: int = 100,
               db_path: str | None = None) -> list[dict]:
    """Récupère les offres, optionnellement filtrées par statut."""
    with get_db(db_path) as conn:
        if statut:
            rows = conn.execute(
                "SELECT * FROM offres WHERE statut = ? ORDER BY date_ajout DESC LIMIT ?",
                (statut, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM offres ORDER BY date_ajout DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


def get_offre_by_id(offre_id: int, db_path: str | None = None) -> dict | None:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM offres WHERE id = ?", (offre_id,)).fetchone()
        return dict(row) if row else None


def update_offre_statut(offre_id: int, statut: str, db_path: str | None = None):
    with get_db(db_path) as conn:
        conn.execute("UPDATE offres SET statut = ? WHERE id = ?", (statut, offre_id))


# ──────────────────────── SCORES ────────────────────────

def insert_score(offre_id: int, score_data: dict, db_path: str | None = None) -> int:
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO scores (offre_id, score, justification,
               competences_matchees, lacunes, conseil, date_calcul)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                offre_id,
                score_data.get("score", 0),
                score_data.get("justification", ""),
                ",".join(score_data.get("competences_matchees", [])),
                ",".join(score_data.get("lacunes", [])),
                score_data.get("conseil", ""),
                datetime.now().isoformat(),
            ),
        )
        return cursor.lastrowid


def get_score_for_offre(offre_id: int, db_path: str | None = None) -> dict | None:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM scores WHERE offre_id = ? ORDER BY date_calcul DESC LIMIT 1",
            (offre_id,),
        ).fetchone()
        return dict(row) if row else None


# ──────────────────────── CVS ────────────────────────

def insert_cv(offre_id: int, cv_data: dict, db_path: str | None = None) -> int:
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO cvs (offre_id, tex_content, pdf_path, filename, date_generation)
               VALUES (?, ?, ?, ?, ?)""",
            (
                offre_id,
                cv_data.get("tex", ""),
                cv_data.get("pdf_path", ""),
                cv_data.get("filename", ""),
                datetime.now().isoformat(),
            ),
        )
        return cursor.lastrowid


def get_cv_for_offre(offre_id: int, db_path: str | None = None) -> dict | None:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM cvs WHERE offre_id = ? ORDER BY date_generation DESC LIMIT 1",
            (offre_id,),
        ).fetchone()
        return dict(row) if row else None


# ──────────────────────── DASHBOARD QUERIES ────────────────────────

def get_offres_with_scores(limit: int = 50, db_path: str | None = None) -> list[dict]:
    """Récupère les offres avec leur score le plus récent, triées par score."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            """SELECT o.*, s.score, s.justification, s.competences_matchees, s.lacunes, s.conseil,
                      c.pdf_path, c.filename AS cv_filename
               FROM offres o
               LEFT JOIN scores s ON s.offre_id = o.id
                   AND s.date_calcul = (SELECT MAX(s2.date_calcul) FROM scores s2 WHERE s2.offre_id = o.id)
               LEFT JOIN cvs c ON c.offre_id = o.id
                   AND c.date_generation = (SELECT MAX(c2.date_generation) FROM cvs c2 WHERE c2.offre_id = o.id)
               ORDER BY COALESCE(s.score, 0) DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_stats(db_path: str | None = None) -> dict:
    """Statistiques globales pour le dashboard."""
    with get_db(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM offres").fetchone()[0]
        scored = conn.execute("SELECT COUNT(DISTINCT offre_id) FROM scores").fetchone()[0]
        cv_gen = conn.execute("SELECT COUNT(DISTINCT offre_id) FROM cvs").fetchone()[0]
        avg_score = conn.execute("SELECT AVG(score) FROM scores").fetchone()[0] or 0
        return {
            "total_offres": total,
            "offres_scorees": scored,
            "cvs_generes": cv_gen,
            "score_moyen": round(avg_score, 1),
        }

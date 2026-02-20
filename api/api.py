#!/usr/bin/env python3
"""
ETL CHALLENGE - API FastAPI (v3)
Conforme au demande du sujet :
  - /ping
  - /siret/{siret}            → format court (rna, name, address)
  - /search?q=...&dept=...    → address_city, is_association
  - /stats/distribution/{cp}  → postal_code, total_active_companies, top_activity
  - /stats/{cp}               → zone, total_entites, repartition, top_naf
  - Codes erreur : 400, 404 au format du sujet
"""

from fastapi import FastAPI, HTTPException, Query
from contextlib import asynccontextmanager
from typing import Optional
import duckdb
import sqlite3
import threading
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DB_PATH     = os.environ.get("DB_PATH",     "duckdb/unified_data.duckdb")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "duckdb/search.db")


# ─────────────────────────────────────────────────────────────────────────────
# POOLS DE CONNEXIONS
# ─────────────────────────────────────────────────────────────────────────────

class DuckDBPool:
    """Connexion DuckDB read-only par thread (évite les reconnexions)."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local  = threading.local()

    def get(self) -> duckdb.DuckDBPyConnection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = duckdb.connect(self.db_path, read_only=True)
            logger.info("Nouvelle connexion DuckDB — thread %s", threading.current_thread().name)
        return self._local.conn


class SQLitePool:
    """Connexion SQLite par thread, mode WAL pour lectures concurrentes."""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local  = threading.local()

    def get(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA query_only=ON")
            logger.info("Nouvelle connexion SQLite — thread %s", threading.current_thread().name)
        return self._local.conn


duck_pool   = DuckDBPool(DB_PATH)
sqlite_pool = SQLitePool(SQLITE_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Démarrage API — pré-chauffe des connexions")
    con  = duck_pool.get()
    n    = con.execute("SELECT COUNT(*) FROM unified_records").fetchone()[0]
    logger.info(f"DuckDB prêt : {n:,} enregistrements")
    conn = sqlite_pool.get()
    nfts = conn.execute("SELECT COUNT(*) FROM search_fts").fetchone()[0]
    logger.info(f"SQLite FTS5 prêt : {nfts:,} entrées")
    yield
    logger.info("Arrêt API")


app = FastAPI(
    title="API ETL Challenge — SIRENE × RNA × BAN",
    version="3.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# SÉCURITÉ : suppression des headers techniques
# ─────────────────────────────────────────────────────────────────────────────

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

HEADERS_TO_REMOVE = {"server", "x-powered-by", "x-aspnet-version", "x-runtime", "x-version"}

class StripTechnicalHeadersMiddleware(BaseHTTPMiddleware):
    """Supprime les headers qui exposent des infos techniques (version serveur, framework…)."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for h in HEADERS_TO_REMOVE:
            response.headers.pop(h, None)
        return response

app.add_middleware(StripTechnicalHeadersMiddleware)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def validate_siret(siret: str):
    """Lève une HTTPException 400 si le SIRET est invalide."""
    if not siret.isdigit() or len(siret) != 14:
        raise HTTPException(status_code=400, detail={
            "error":   "INVALID_FORMAT",
            "message": "Le siret doit contenir 14 chiffres."
        })

def validate_postal(cp: str):
    """Lève une HTTPException 400 si le code postal est invalide."""
    if not cp.isdigit() or len(cp) != 5:
        raise HTTPException(status_code=400, detail={
            "error":   "INVALID_FORMAT",
            "message": "Le code postal doit contenir 5 chiffres."
        })


# ─────────────────────────────────────────────────────────────────────────────
# A. HEALTHCHECK — GET /api/v1/ping
# Réponse : {"status": "ok"}
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/ping")
def ping():
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# B. GOLDEN RECORD — GET /api/v1/siret/{siret}
#
# Format de réponse :
# {
#   "siret": "...",
#   "rna": "W751000060" | null,
#   "name": "...",
#   "status": "open" | "closed",
#   "nature": "ASSOCIATION" | null,
#   "address": {
#     "number": "98",
#     "street": "RUE DIDOT",
#     "postal_code": "75014",
#     "city": "PARIS",
#     "is_ban_validated": true,
#     "latitude": 48.8296,
#     "longitude": 2.3235
#   }
# }
#
# Erreurs :
#   400 : {"error": "INVALID_FORMAT", "message": "..."}
#   404 : {"error": "Siret not found", "input": "<siret>"}
#         ↑ Format EXACT du sujet (pas SIRET_NOT_FOUND)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/siret/{siret}")
def get_siret(siret: str):
    validate_siret(siret)

    con = duck_pool.get()
    row = con.execute("""
        SELECT
            siret,
            name,
            id_rna,
            status,
            asso_nature,
            addr_num,
            addr_type,
            addr_street,
            postal_code,
            city,
            is_ban_validated,
            latitude,
            longitude
        FROM unified_records
        WHERE siret = ?
        LIMIT 1
    """, [siret]).fetchone()

    # 404 — format EXACT du sujet (exemple 3)
    if not row:
        raise HTTPException(status_code=404, detail={
            "error": "Siret not found",
            "input": siret
        })

    (
        siret_, name, id_rna, status, nature,
        addr_num, addr_type, addr_street,
        postal_code, city,
        is_ban, lat, lon
    ) = row

    # Construction de la rue : "RUE DIDOT" (type + libellé)
    parts  = [p for p in [addr_type, addr_street] if p]
    street = " ".join(parts) if parts else None

    return {
        "siret":  siret_,
        "rna":    id_rna,           # null si pas association
        "name":   name,
        "status": status,
        "nature": nature,           # "ASSOCIATION" ou null
        "address": {
            "number":           addr_num or None,
            "street":           street,
            "postal_code":      postal_code,
            "city":             city,
            "is_ban_validated": bool(is_ban) if is_ban is not None else False,
            "latitude":         float(lat) if lat is not None else None,
            "longitude":        float(lon) if lon is not None else None,
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# C. RECHERCHE FULL-TEXT — GET /api/v1/search
#
# Paramètres acceptés :
#   q           : terme de recherche (obligatoire)
#   dept        : code département 2 chiffres (ex: "69")
#   postal_code : code postal 5 chiffres (ex: "69001")
#
# Format de réponse :
# {
#   "query": "boulangerie",
#   "filter_dept": "69",
#   "count": 2,
#   "results": [
#     {
#       "siret": "...",
#       "name": "...",
#       "address_city": "LYON",     ← "address_city" et non "city"
#       "is_association": true
#     }
#   ]
# }
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/search")
def search(
    q:           str           = Query(..., description="Terme de recherche"),
    dept:        Optional[str] = Query(None, description="Code département (ex: 69)"),
    postal_code: Optional[str] = Query(None, description="Code postal exact (ex: 69001)"),
):
    q_clean = q.strip()
    if not q_clean:
        raise HTTPException(status_code=400, detail={
            "error":   "INVALID_FORMAT",
            "message": "Le paramètre q ne peut pas être vide."
        })

    conn = sqlite_pool.get()

    # Requête FTS5 avec wildcard partielle (boulang* → boulangerie)
    fts_query = " ".join(f"{word}*" for word in q_clean.split())

    # Jointure FTS (recherche texte) + META (filtres géo avec index B-tree)
    conditions = []
    params     = []

    if dept:
        conditions.append("m.dept = ?")
        params.append(dept.strip().zfill(2))
    if postal_code:
        conditions.append("m.postal_code = ?")
        params.append(postal_code.strip().zfill(5))

    join_condition = "f.siret = m.siret"
    if conditions:
        join_condition += " AND " + " AND ".join(conditions)

    sql = f"""
        SELECT f.siret, f.name, f.city, f.is_association
        FROM search_fts f
        JOIN search_meta m ON {join_condition}
        WHERE search_fts MATCH ?
        ORDER BY rank
        LIMIT 10
    """
    params.append(fts_query)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"FTS5 erreur ({e}), fallback LIKE pour q='{q_clean}'")
        rows = _search_fallback(conn, q_clean, dept, postal_code)

    return {
        "query":       q,
        "filter_dept": dept,
        "count":       len(rows),
        "results": [
            {
                "siret":          r[0],
                "name":           r[1],
                "address_city":   r[2],
                "is_association": bool(r[3]),
            }
            for r in rows
        ],
    }


def _search_fallback(conn, q, dept, postal_code):
    """Fallback LIKE si FTS5 échoue (caractères spéciaux rares)."""
    conditions = ["(name LIKE ? OR enseigne LIKE ?)"]
    params     = [f"%{q.upper()}%", f"%{q.upper()}%"]
    if dept:
        conditions.append("dept = ?")
        params.append(dept.strip().zfill(2))
    if postal_code:
        conditions.append("postal_code = ?")
        params.append(postal_code.strip().zfill(5))
    sql = "SELECT siret, name, city, is_association FROM search_meta WHERE " \
          + " AND ".join(conditions) + " LIMIT 10"
    return conn.execute(sql, params).fetchall()


# ─────────────────────────────────────────────────────────────────────────────
# D. STATS FORMAT  — GET /api/v1/stats/distribution/{code_postal}
#
# Format de réponse :
# {
#   "postal_code": "75013",
#   "total_active_companies": 14502,
#   "total_associations": 3200,
#   "top_activity": "6201Z"
# }
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/stats/distribution/{code_postal}")
def get_stats_distribution(code_postal: str):
    validate_postal(code_postal)

    con = duck_pool.get()
    row = con.execute("""
        SELECT
            total_entites,
            total_associations,
            top_naf_code
        FROM stats_by_postal
        WHERE postal_code = ?
        LIMIT 1
    """, [code_postal]).fetchone()

    if not row or row[0] == 0:
        raise HTTPException(status_code=404, detail={
            "error":   "POSTAL_NOT_FOUND",
            "message": f"Aucune entité trouvée pour le code postal {code_postal}."
        })

    total, nb_asso, top_naf = row

    return {
        "postal_code":            code_postal,
        "total_active_companies": total,
        "total_associations":     nb_asso,
        "top_activity":           top_naf,
    }


# ─────────────────────────────────────────────────────────────────────────────
# E. STATS FORMAT — GET /api/v1/stats/{code_postal}
#
# Format de réponse :
# {
#   "zone": "33000",
#   "total_entites": 15420,
#   "repartition": {
#     "entreprises_pures": 14200,
#     "associations": 1220,
#     "etablissements_fermes": 3400
#   },
#   "top_naf": {
#     "code": "56.10A",
#     "libelle": null,
#     "count": 850
#   }
# }
#
# IMPORTANT : cette route doit être déclarée APRÈS /stats/distribution/{cp}
# sinon FastAPI intercepterait "distribution" comme un code_postal.
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/stats/{code_postal}")
def get_stats(code_postal: str):
    validate_postal(code_postal)

    con = duck_pool.get()
    row = con.execute("""
        SELECT
            total_entites,
            total_associations,
            entreprises_pures,
            etablissements_fermes,
            top_naf_code,
            top_naf_count
        FROM stats_by_postal
        WHERE postal_code = ?
        LIMIT 1
    """, [code_postal]).fetchone()

    if not row or row[0] == 0:
        raise HTTPException(status_code=404, detail={
            "error":   "POSTAL_NOT_FOUND",
            "message": f"Aucune entité trouvée pour le code postal {code_postal}."
        })

    total, nb_asso, nb_ent, nb_closed, top_naf, top_naf_cnt = row

    return {
        "zone":          code_postal,
        "total_entites": total,
        "repartition": {
            "entreprises_pures":     nb_ent,
            "associations":          nb_asso,
            "etablissements_fermes": nb_closed,
        },
        "top_naf": {
            "code":    top_naf,
            "libelle": None,
            "count":   top_naf_cnt,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# LANCEMENT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        workers=4,
        log_level="info",
        server_header=False,  
        date_header=False,
    )
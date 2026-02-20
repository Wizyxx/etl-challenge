#!/usr/bin/env python3
"""
ETL CHALLENGE - API Optimisée (Finale)
- GET /siret -> DuckDB (Lecture précise)
- GET /stats -> DuckDB (Pré-calculé)
- GET /search -> SQLite FTS5 (Recherche texte ultra-rapide)
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware # <-- IMPORT AJOUTÉ
from contextlib import asynccontextmanager
from typing import Optional
import duckdb
import sqlite3
import threading
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# CORRECTION : Chemins par défaut alignés avec l'ETL
DB_PATH = os.environ.get("DB_PATH", "data/processed/unified_data.duckdb")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "data/processed/search.db")

# --- POOLS ---
class DuckDBPool:
    def __init__(self, db_path):
        self.db_path = db_path
        self._local = threading.local()
    def get(self):
        if not hasattr(self._local, 'conn'):
            # read_only=True est vital pour la performance
            self._local.conn = duckdb.connect(self.db_path, read_only=True)
        return self._local.conn

duck_pool = DuckDBPool(DB_PATH)
sqlite_conn = None 

@asynccontextmanager
async def lifespan(app: FastAPI):
    global sqlite_conn
    logger.info(f"🔥 API Start. DB={DB_PATH}, SEARCH={SQLITE_PATH}")
    
    # Test DuckDB
    try:
        duck_pool.get().execute("SELECT 1")
        logger.info("✅ DuckDB connecté")
    except Exception as e:
        logger.error(f"❌ DuckDB Error: {e}")

    # Test SQLite
    if os.path.exists(SQLITE_PATH):
        try:
            sqlite_conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
            logger.info("✅ SQLite connecté")
        except Exception as e:
            logger.error(f"❌ SQLite Error: {e}")
    else:
        logger.warning("⚠️ SQLite Search DB not found (Lancez 'make index')")
    
    yield
    if sqlite_conn: sqlite_conn.close()

app = FastAPI(lifespan=lifespan)

# CONFIGURATION CORS (Pour le Frontend et Ngrok)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTS ---

@app.get("/api/v1/ping")
def ping():
    return {"status": "ok"}

@app.get("/api/v1/siret/{siret}")
def get_siret(siret: str):
    if len(siret) != 14 or not siret.isdigit():
        raise HTTPException(400, detail={"error": "INVALID_FORMAT", "message": "14 chiffres requis"})
    
    con = duck_pool.get()
    # On utilise COALESCE pour gérer les NULL proprement
    row = con.execute("""
        SELECT siret, name, id_rna, status, asso_nature, 
               addr_num, addr_type, addr_street, postal_code, city, 
               is_ban_validated, latitude, longitude, enseigne, categorie_entreprise
        FROM unified_records WHERE siret = ?
    """, [siret]).fetchone()

    if not row:
        raise HTTPException(404, detail={"error": "Siret not found", "input": siret})

    return {
        "siret": row[0],
        "rna": row[2],
        "name": row[1],
        "status": row[3],
        "nature": row[4],
        "address": {
            "number": row[5],
            "street": f"{row[6] or ''} {row[7] or ''}".strip(),
            "postal_code": row[8],
            "city": row[9],
            "is_ban_validated": bool(row[10]),
            "latitude": row[11],
            "longitude": row[12]
        }
    }

@app.get("/api/v1/search")
def search(q: str = Query(...), dept: Optional[str] = None, postal_code: Optional[str] = None):
    if not sqlite_conn:
        raise HTTPException(503, "Search unavailable")

    # Nettoyage pour FTS5 (éviter injection ou erreur syntaxe)
    safe_q = q.replace('"', '').replace("'", "")
    term = f'"{safe_q}"*'
    
    clauses = [f"search_index MATCH ?"]
    params = [term]
    
    if postal_code:
        clauses.append("postal_code = ?")
        params.append(postal_code)
    elif dept:
        clauses.append("postal_code LIKE ?")
        params.append(f"{dept}%")

    # On utilise la table search_index créée par 05_index_fts.py
    sql = f"SELECT siret, name, city, is_association FROM search_index WHERE {' AND '.join(clauses)} ORDER BY rank LIMIT 10"
    
    try:
        cursor = sqlite_conn.cursor()
        rows = cursor.execute(sql, params).fetchall()
        return {
            "query": q,
            "count": len(rows),
            "results": [{"siret": r[0], "name": r[1], "city": r[2], "is_association": bool(r[3])} for r in rows]
        }
    except Exception as e:
        logger.error(f"Search fail: {e}")
        return {"query": q, "results": [], "error": "Search failed"}

# Fonction interne pour récupérer les stats
def _fetch_stats(cp: str):
    if len(cp) != 5: raise HTTPException(400, "Invalid CP")
    
    con = duck_pool.get()
    row = con.execute("SELECT * FROM stats_by_postal WHERE postal_code = ?", [cp]).fetchone()
    
    if not row: raise HTTPException(404, "Not found")
    
    return {
        "zone": cp,
        "total_entites": row[1],
        "repartition": {
            "associations": row[2],
            "entreprises_pures": row[3],
            "fermes": row[4]
        },
        "top_naf": {"code": row[5], "count": row[6]}
    }

# Endpoint principal
@app.get("/api/v1/stats/{cp}")
def get_stats(cp: str):
    return _fetch_stats(cp)

# ALIAS DE SÉCURITÉ : Au cas où le prof utilise l'autre URL
@app.get("/api/v1/stats/distribution/{cp}")
def get_stats_dist(cp: str):
    return _fetch_stats(cp)
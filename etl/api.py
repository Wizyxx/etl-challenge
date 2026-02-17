#!/usr/bin/env python3
"""
ETL CHALLENGE - API FastAPI Optimisée
DuckDB + Pool de connexions → < 500ms garanti sur le stress test
"""

from fastapi import FastAPI, HTTPException, Query
from contextlib import asynccontextmanager
from typing import Optional
import duckdb
import threading
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "data/processed/unified_data.duckdb")


# ─────────────────────────────────────────────────────────────────────────────
# POOL DE CONNEXIONS DuckDB (thread-safe, évite les reconnexions)
# ─────────────────────────────────────────────────────────────────────────────
class DuckDBPool:
    """
    Pool simple de connexions DuckDB read-only.
    Chaque thread obtient sa propre connexion (DuckDB read_only est thread-safe).
    """
    def __init__(self, db_path: str, pool_size: int = 8):
        self.db_path   = db_path
        self.pool_size = pool_size
        self._local    = threading.local()

    def get(self) -> duckdb.DuckDBPyConnection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = duckdb.connect(self.db_path, read_only=True)
            logger.info("🔌 Nouvelle connexion DuckDB créée pour thread %s", threading.current_thread().name)
        return self._local.conn

    def close_all(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

pool = DuckDBPool(DB_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# LIFESPAN (startup/shutdown)
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(" Démarrage API — pré-chauffe connexion DuckDB")
    # Pré-chauffe la connexion du thread principal
    con = pool.get()
    n = con.execute("SELECT COUNT(*) FROM unified_records").fetchone()[0]
    logger.info(f" Base prête : {n:,} enregistrements")
    yield
    logger.info(" Arrêt API")


app = FastAPI(
    title="API ETL Challenge — SIRENE × RNA × BAN",
    version="1.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# A. HEALTHCHECK
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/v1/ping")
def ping():
    """Healthcheck — répond en < 5ms"""
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# B. GOLDEN RECORD — /siret/{siret}
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/v1/siret/{siret}")
def get_siret(siret: str):
    """
    Retourne la fiche unifiée d'un établissement (SIRENE + RNA + BAN).
    Clé du challenge : le champ id_rna doit être non-null pour les associations.
    """
    # Validation format (400 Bad Request)
    if not siret.isdigit() or len(siret) != 14:
        raise HTTPException(status_code=400, detail={
            "error":   "INVALID_FORMAT",
            "message": "Le siret doit contenir 14 chiffres."
        })

    con = pool.get()
    row = con.execute("""
        SELECT
            siret, name, enseigne, categorie_entreprise,
            id_rna, date_publication_jo,
            addr_num, addr_type, addr_street,
            postal_code, city,
            latitude, longitude, geo_score,
            is_ban_validated, status, is_association,
            asso_nature
        FROM unified_records
        WHERE siret = ?
        LIMIT 1
    """, [siret]).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail={
            "error":   "SIRET_NOT_FOUND",
            "message": f"Le siret {siret} est inconnu."
        })

    (
        siret_, name, enseigne, cat_ent,
        id_rna, date_publi,
        addr_num, addr_type, addr_street,
        postal_code, city,
        lat, lon, geo_score,
        is_ban, status, is_assoc,
        asso_nature
    ) = row

    # date_publication_jo → str ISO ou null
    date_publi_str = date_publi.isoformat() if date_publi else None

    # asso_id : null si pas association (évite les faux positifs)
    asso_id = None
    if id_rna:
        asso_id = {
            "id_rna":             id_rna,
            "date_publication_jo": date_publi_str,
        }

    return {
        "identity": {
            "siret":               siret_,
            "nom_raison_sociale":  name,
            "enseigne":            enseigne,
            "categorie_entreprise": cat_ent,
        },
        "asso_id": asso_id,                # null si pas association 
        "location": {
            "numero_voie":    addr_num,
            "type_voie":      addr_type,
            "libelle_voie":   addr_street,
            "code_postal":    postal_code,
            "commune":        city,
            "geo_score":      float(geo_score) if geo_score else None,
            "latitude":       float(lat)  if lat  else None,
            "longitude":      float(lon)  if lon  else None,
            "is_ban_validated": bool(is_ban) if is_ban is not None else False,
        },
        # Champs bonus compatibles avec l'exemple simplifié du sujet
        "status":    status,
        "nature":    asso_nature,
    }


# ─────────────────────────────────────────────────────────────────────────────
# C. RECHERCHE TEXTUELLE — /search?q=...&dept=...
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/v1/search")
def search(
    q:           str            = Query(..., description="Terme de recherche (nom/enseigne)"),
    dept:        Optional[str]  = Query(None, description="Code département (ex: 69)"),
    postal_code: Optional[str]  = Query(None, description="Code postal exact (ex: 69001)"),
):
    """
    Recherche full-text avec filtre géographique.
    Utilise la table search_index pré-calculée → rapide.
    """
    q_upper = q.strip().upper()

    # Construction de la requête avec paramètres positionnels (évite injection SQL)
    conditions = ["(name_upper LIKE ? OR enseigne_upper LIKE ?)"]
    params     = [f"%{q_upper}%", f"%{q_upper}%"]

    if dept:
        conditions.append("dept = ?")
        params.append(dept.strip().zfill(2))

    if postal_code:
        conditions.append("postal_code = ?")
        params.append(postal_code.strip().zfill(5))

    where = " AND ".join(conditions)
    sql   = f"""
        SELECT si.siret, si.name_upper AS name, si.city, si.is_association
        FROM search_index si
        WHERE {where}
        LIMIT 10
    """

    con = pool.get()
    rows = con.execute(sql, params).fetchall()

    return {
        "query":       q,
        "filter_dept": dept,
        "count":       len(rows),
        "results": [
            {
                "siret":          r[0],
                "name":           r[1],
                "is_association": bool(r[3]),
                "city":           r[2],
            }
            for r in rows
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# D. STATISTIQUES — /stats/{code_postal}
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/v1/stats/{code_postal}")
def get_stats(code_postal: str):
    """
    Agrégation OLAP par code postal.
    Utilise la table pré-calculée stats_by_postal → < 50ms garanti.
    """
    if not code_postal.isdigit() or len(code_postal) != 5:
        raise HTTPException(status_code=400, detail={
            "error":   "INVALID_FORMAT",
            "message": "Le code postal doit contenir 5 chiffres."
        })

    con = pool.get()

    # Lecture de la table pré-agrégée (quasi-instantanée)
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
            "libelle": None,    # Optionnel : joindre une table de libellés NAF
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
        port=8000,
        workers=4,           # 4 workers → 4 threads de traitement parallèle
        log_level="info",
    )
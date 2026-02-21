#!/usr/bin/env python3
"""
ETL CHALLENGE - PHASE 3: CHARGEMENT (v8 - SANS FUZZY)
Suppression du niveau 3 (fuzzy matching) qui prenait 6h.
Matching RNA en 2 niveaux uniquement :
  - Niveau 1 : SIRET exact (score 1.0)
  - Niveau 2 : SIREN exact (score 0.95)
"""

import duckdb
import sqlite3
import logging
import pandas as pd
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROCESSED   = Path("data_parquet")
DB_DIR      = Path("duckdb")
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH     = DB_DIR / "unified_data.duckdb"
SQLITE_PATH = DB_DIR / "search.db"


def load_and_join():
    logger.info("Connexion DuckDB : %s", DB_PATH)

    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))

    con.execute("PRAGMA memory_limit='26GB'")
    con.execute("PRAGMA threads=8")

    # =========================================================================
    # 1. CHARGEMENT DES PARQUETS
    # =========================================================================
    logger.info("Chargement SIRENE...")
    con.execute(f"CREATE TABLE sirene AS SELECT * FROM read_parquet('{PROCESSED}/sirene_clean.parquet')")
    n = con.execute("SELECT COUNT(*) FROM sirene").fetchone()[0]
    logger.info(f"   {n:,} etablissements")

    logger.info("Chargement RNA...")
    con.execute(f"CREATE TABLE rna AS SELECT * FROM read_parquet('{PROCESSED}/rna_clean.parquet')")
    n = con.execute("SELECT COUNT(*) FROM rna").fetchone()[0]
    logger.info(f"   {n:,} associations")

    logger.info("Chargement BAN...")
    con.execute(f"CREATE TABLE ban AS SELECT * FROM read_parquet('{PROCESSED}/ban_clean.parquet')")
    n = con.execute("SELECT COUNT(*) FROM ban").fetchone()[0]
    logger.info(f"   {n:,} adresses")

    logger.info("Chargement UniteLegale (noms)...")
    ul_path = PROCESSED / "unite_legale_raw.parquet"
    if ul_path.exists():
        con.execute(f"""
            CREATE TABLE unite_legale AS
            SELECT
                siren,
                UPPER(COALESCE(
                    NULLIF(TRIM(denominationUniteLegale), ''),
                    NULLIF(TRIM(COALESCE(prenom1UniteLegale,'') || ' ' || COALESCE(nomUniteLegale,'')), ''),
                    NULL
                )) AS nom_ul,
                categorieEntreprise
            FROM read_parquet('{ul_path}')
            WHERE siren IS NOT NULL
        """)
        n = con.execute("SELECT COUNT(*) FROM unite_legale").fetchone()[0]
        logger.info(f"   {n:,} unites legales")
    else:
        logger.warning("   unite_legale absent, noms incomplets")
        con.execute("CREATE TABLE unite_legale (siren VARCHAR, nom_ul VARCHAR, categorieEntreprise VARCHAR)")

    # =========================================================================
    # 2. TABLE DE LIAISON siret_rna_link (2 niveaux uniquement)
    # =========================================================================
    logger.info("Construction de la table siret_rna_link...")

    # --- Niveau 1 : SIRET exact (14 chiffres) → score 1.0 ---
    logger.info("   Niveau 1 — SIRET exact (14 chiffres)...")
    con.execute("""
        CREATE TABLE siret_rna_link AS
        SELECT
            s.siret,
            r.id_rna,
            1.0           AS match_score,
            'SIRET_EXACT' AS match_method,
            r.date_publi,
            r.nature
        FROM sirene s
        INNER JOIN rna r ON s.siret = r.siret
        WHERE r.siret IS NOT NULL
    """)
    n1 = con.execute("SELECT COUNT(*) FROM siret_rna_link").fetchone()[0]
    logger.info(f"      -> {n1:,} matchs niveau 1")

    # --- Niveau 2 : SIREN (9 chiffres) → score 0.95 ---
    logger.info("   Niveau 2 — SIREN (9 chiffres)...")
    con.execute("""
        INSERT INTO siret_rna_link
        SELECT
            s.siret,
            t.id_rna,
            0.95          AS match_score,
            'SIREN_EXACT' AS match_method,
            t.date_publi,
            t.nature
        FROM sirene s
        INNER JOIN (
            SELECT
                id_rna,
                LEFT(siret, 9) AS siren_key,
                date_publi,
                nature,
                ROW_NUMBER() OVER (PARTITION BY LEFT(siret, 9) ORDER BY id_rna) AS rn
            FROM rna
            WHERE siret IS NOT NULL
        ) t ON s.siren = t.siren_key AND t.rn = 1
        WHERE s.siret NOT IN (SELECT siret FROM siret_rna_link)
    """)
    n2 = con.execute("SELECT COUNT(*) FROM siret_rna_link").fetchone()[0] - n1
    logger.info(f"      -> {n2:,} matchs niveau 2")

    n_total = con.execute("SELECT COUNT(*) FROM siret_rna_link").fetchone()[0]
    logger.info(f"   TOTAL siret_rna_link : {n_total:,} liaisons")

    con.execute("CREATE INDEX idx_link_siret ON siret_rna_link(siret)")
    con.execute("CREATE INDEX idx_link_rna   ON siret_rna_link(id_rna)")

    # =========================================================================
    # 3. TABLE UNIFIEE (golden_record)
    # =========================================================================
    logger.info("Creation table unifiee...")
    con.execute("""
        CREATE TABLE unified_records AS
        SELECT
            s.siret,
            s.siren,
            COALESCE(NULLIF(s.name_etab, ''), NULLIF(s.enseigne, ''), ul.nom_ul) AS name,
            COALESCE(NULLIF(s.enseigne, ''), ul.nom_ul) AS enseigne,
            s.addr_num, s.addr_rep, s.addr_type, s.addr_street,
            s.postal_code, s.city, s.commune_id,
            s.naf, s.status,
            ul.categorieEntreprise AS categorie_entreprise,
            s.ban_key, s.etablissementSiege, s.caractereEmployeurEtablissement,
            lnk.id_rna,
            lnk.date_publi         AS date_publication_jo,
            lnk.id_rna IS NOT NULL AS is_association,
            lnk.nature             AS asso_nature,
            lnk.match_score        AS rna_match_score,
            lnk.match_method       AS rna_match_method,
            b.lat                  AS latitude,
            b.lon                  AS longitude,
            CASE WHEN b.ban_key IS NOT NULL THEN 1.0 ELSE NULL END AS geo_score,
            (b.ban_key IS NOT NULL) AS is_ban_validated
        FROM sirene s
        LEFT JOIN unite_legale ul    ON s.siren = ul.siren
        LEFT JOIN siret_rna_link lnk ON s.siret = lnk.siret
        LEFT JOIN ban b              ON s.ban_key = b.ban_key
    """)

    n     = con.execute("SELECT COUNT(*) FROM unified_records").fetchone()[0]
    n_rna = con.execute("SELECT COUNT(*) FROM unified_records WHERE id_rna IS NOT NULL").fetchone()[0]
    n_gps = con.execute("SELECT COUNT(*) FROM unified_records WHERE latitude IS NOT NULL").fetchone()[0]
    logger.info(f"   Table unifiee : {n:,} enregistrements")
    logger.info(f"   Avec RNA      : {n_rna:,}")
    logger.info(f"   Avec GPS      : {n_gps:,}")

    dist = con.execute("""
        SELECT rna_match_method, COUNT(*) AS cnt
        FROM unified_records WHERE id_rna IS NOT NULL
        GROUP BY rna_match_method ORDER BY cnt DESC
    """).fetchall()
    for method, cnt in dist:
        logger.info(f"      {method:<15} : {cnt:,}")

    # --- VERIFICATION GOLDEN CASE CROIX ROUGE ---
    res = con.execute("""
        SELECT siret, name, id_rna, latitude, longitude, rna_match_score, rna_match_method
        FROM unified_records WHERE siret = '77567227200020'
    """).fetchone()
    if res:
        logger.info(f"GOLDEN CASE — Croix Rouge : {res}")
        logger.info("   PREUVE 1 (RNA) : %s", "OK id_rna=" + str(res[2]) if res[2] else "ECHEC id_rna=NULL")
        logger.info("   PREUVE 2 (GPS) : %s", "OK" if res[3] else "ECHEC lat=NULL")
        logger.info("   MATCH  : score=%.2f method=%s", res[5] or 0, res[6] or "NONE")
    else:
        logger.warning("SIRET Croix Rouge absent de unified_records !")

    # =========================================================================
    # 4. INDEX DUCKDB
    # =========================================================================
    logger.info("Creation des index DuckDB...")
    con.execute("CREATE INDEX idx_siret  ON unified_records(siret)")
    con.execute("CREATE INDEX idx_postal ON unified_records(postal_code)")
    con.execute("CREATE INDEX idx_name   ON unified_records(name)")
    con.execute("CREATE INDEX idx_siren  ON unified_records(siren)")
    logger.info("   idx_siret / idx_postal / idx_name / idx_siren OK")

    # =========================================================================
    # 5. STATS PRE-AGREGEES (pour /stats/{cp})
    # =========================================================================
    logger.info("Pre-calcul statistiques par code postal...")
    con.execute("""
        CREATE TABLE stats_by_postal AS
        SELECT
            postal_code,
            COUNT(*)                                            AS total_entites,
            COUNT(CASE WHEN is_association = TRUE  THEN 1 END) AS total_associations,
            COUNT(CASE WHEN is_association = FALSE THEN 1 END) AS entreprises_pures,
            COUNT(CASE WHEN status = 'closed'      THEN 1 END) AS etablissements_fermes,
            mode(naf)                                          AS top_naf_code
        FROM unified_records
        WHERE postal_code IS NOT NULL
        GROUP BY postal_code
    """)

    con.execute("""
        CREATE TABLE naf_counts AS
        SELECT postal_code, naf, COUNT(*) AS cnt
        FROM unified_records
        WHERE postal_code IS NOT NULL AND naf IS NOT NULL
        GROUP BY postal_code, naf
    """)
    con.execute("ALTER TABLE stats_by_postal ADD COLUMN top_naf_count BIGINT")
    con.execute("""
        UPDATE stats_by_postal s
        SET top_naf_count = (
            SELECT cnt FROM naf_counts n
            WHERE n.postal_code = s.postal_code AND n.naf = s.top_naf_code
            LIMIT 1
        )
    """)
    con.execute("DROP TABLE naf_counts")
    con.execute("CREATE INDEX idx_stats_postal ON stats_by_postal(postal_code)")
    logger.info("   stats_by_postal OK (avec top_naf_count)")

    # =========================================================================
    # 6. SQLITE FTS5 (pour /search)
    # =========================================================================
    logger.info("Export vers SQLite FTS5...")
    _build_sqlite_fts(con)

    con.close()
    logger.info("=" * 60)
    logger.info("BASE DUCKDB PRETE  : %s", DB_PATH)
    logger.info("BASE SQLITE PRETE  : %s", SQLITE_PATH)
    logger.info("=" * 60)


def _build_sqlite_fts(con_duck: duckdb.DuckDBPyConnection):
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()

    conn = sqlite3.connect(str(SQLITE_PATH))
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE VIRTUAL TABLE search_fts USING fts5(
            siret          UNINDEXED,
            name,
            enseigne,
            city           UNINDEXED,
            postal_code    UNINDEXED,
            dept           UNINDEXED,
            is_association UNINDEXED,
            status         UNINDEXED,
            tokenize = 'unicode61 remove_diacritics 1'
        )
    """)
    conn.execute("""
        CREATE TABLE search_meta (
            siret          TEXT PRIMARY KEY,
            name           TEXT,
            enseigne       TEXT,
            city           TEXT,
            postal_code    TEXT,
            dept           TEXT,
            is_association INTEGER,
            status         TEXT
        )
    """)
    conn.execute("CREATE INDEX idx_meta_dept   ON search_meta(dept)")
    conn.execute("CREATE INDEX idx_meta_postal ON search_meta(postal_code)")

    logger.info("   Export des donnees depuis DuckDB...")

    BATCH  = 500_000
    offset = 0
    total  = 0

    while True:
        rows = con_duck.execute(f"""
            SELECT
                siret,
                COALESCE(name, '')        AS name,
                COALESCE(enseigne, '')    AS enseigne,
                COALESCE(city, '')        AS city,
                COALESCE(postal_code, '') AS postal_code,
                COALESCE(SUBSTR(postal_code, 1, 2), '') AS dept,
                CAST(is_association AS INTEGER),
                COALESCE(status, '')      AS status
            FROM unified_records
            WHERE name IS NOT NULL AND postal_code IS NOT NULL
            LIMIT {BATCH} OFFSET {offset}
        """).fetchall()

        if not rows:
            break

        conn.executemany("INSERT INTO search_fts VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.executemany("INSERT OR IGNORE INTO search_meta VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.commit()

        total  += len(rows)
        offset += BATCH
        logger.info(f"   -> {total:,} entrees indexees...")

    logger.info("   Optimisation de l'index FTS5 (merge)...")
    conn.execute("INSERT INTO search_fts(search_fts) VALUES('optimize')")
    conn.commit()
    conn.close()

    logger.info(f"OK SQLite FTS5 : {total:,} entrees -> {SQLITE_PATH}")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("PHASE 3 - CHARGEMENT & JOINTURES (v8 - SANS FUZZY)")
    logger.info("=" * 60)
    load_and_join()
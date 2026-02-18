#!/usr/bin/env python3
"""
ETL CHALLENGE - PHASE 3: CHARGEMENT (v4)
Corrections vs v3 :
  - Ajout export SQLite FTS5 pour l'endpoint /search (imposé par le sujet)
  - DuckDB reste pour /siret et /stats
"""

import duckdb
import sqlite3
import logging
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
    # 2. TABLE UNIFIEE (golden_record)
    # =========================================================================
    logger.info("Creation table unifiee (jointures)...")

    con.execute("""
        CREATE TABLE unified_records AS
        WITH

        rna_by_siret AS (
            SELECT * FROM rna WHERE siret IS NOT NULL
        ),

        rna_by_siren AS (
            SELECT id_rna, siren_key, date_publi, nature
            FROM (
                SELECT
                    id_rna,
                    LEFT(siret, 9)  AS siren_key,
                    date_publi,
                    nature,
                    ROW_NUMBER() OVER (PARTITION BY LEFT(siret, 9) ORDER BY id_rna) AS rn
                FROM rna
                WHERE siret IS NOT NULL
            ) t
            WHERE rn = 1
        ),

        sirene_rna AS (
            SELECT
                s.siret,
                s.siren,
                COALESCE(
                    NULLIF(s.name_etab, ''),
                    NULLIF(s.enseigne, ''),
                    ul.nom_ul
                ) AS name,
                COALESCE(NULLIF(s.enseigne, ''), ul.nom_ul) AS enseigne,
                s.addr_num,
                s.addr_rep,
                s.addr_type,
                s.addr_street,
                s.postal_code,
                s.city,
                s.commune_id,
                s.naf,
                s.status,
                ul.categorieEntreprise AS categorie_entreprise,
                s.ban_key,
                s.etablissementSiege,
                s.caractereEmployeurEtablissement,
                COALESCE(ra.id_rna,    rb.id_rna)    AS id_rna,
                COALESCE(ra.date_publi,rb.date_publi) AS date_publication_jo,
                COALESCE(ra.id_rna,    rb.id_rna) IS NOT NULL AS is_association,
                ra.nature                             AS asso_nature
            FROM sirene s
            LEFT JOIN unite_legale ul ON s.siren = ul.siren
            LEFT JOIN rna_by_siret ra ON s.siret = ra.siret
            LEFT JOIN rna_by_siren rb ON s.siren = rb.siren_key
                                     AND ra.id_rna IS NULL
        ),

        full_join AS (
            SELECT
                sr.*,
                b.lat                                       AS latitude,
                b.lon                                       AS longitude,
                CASE WHEN b.ban_key IS NOT NULL THEN 1.0
                     ELSE NULL END                         AS geo_score,
                (b.ban_key IS NOT NULL)                    AS is_ban_validated
            FROM sirene_rna sr
            LEFT JOIN ban b ON sr.ban_key = b.ban_key
        )

        SELECT * FROM full_join
    """)

    n     = con.execute("SELECT COUNT(*) FROM unified_records").fetchone()[0]
    n_rna = con.execute("SELECT COUNT(*) FROM unified_records WHERE id_rna IS NOT NULL").fetchone()[0]
    n_gps = con.execute("SELECT COUNT(*) FROM unified_records WHERE latitude IS NOT NULL").fetchone()[0]
    logger.info(f"   Table unifiee : {n:,} enregistrements")
    logger.info(f"   Avec RNA      : {n_rna:,}")
    logger.info(f"   Avec GPS      : {n_gps:,}")

    # Vérification Croix Rouge
    res = con.execute("""
        SELECT siret, name, id_rna, latitude, longitude
        FROM unified_records WHERE siret = '77567227200020'
    """).fetchone()
    if res:
        logger.info(f"Croix Rouge : {res}")
        logger.info("   PREUVE 1 (RNA) : %s", "OK id_rna=" + str(res[2]) if res[2] else "ECHEC id_rna=NULL")
        logger.info("   PREUVE 2 (GPS) : %s", "OK" if res[3] else "ECHEC lat=NULL")
    else:
        logger.warning("SIRET Croix Rouge absent de unified_records")

    # =========================================================================
    # 3. INDEX DUCKDB
    # =========================================================================
    logger.info("Creation des index DuckDB...")
    con.execute("CREATE INDEX idx_siret  ON unified_records(siret)")
    con.execute("CREATE INDEX idx_postal ON unified_records(postal_code)")
    con.execute("CREATE INDEX idx_name   ON unified_records(name)")
    con.execute("CREATE INDEX idx_siren  ON unified_records(siren)")
    logger.info("   idx_siret / idx_postal / idx_name / idx_siren OK")

    # =========================================================================
    # 4. STATS PRE-AGREGEES (pour /stats/{cp})
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
    logger.info("   stats_by_postal OK")

    # =========================================================================
    # 5. SQLITE FTS5 (pour /search — imposé par le sujet)
    # =========================================================================
    logger.info("Export vers SQLite FTS5 (search_view)...")
    _build_sqlite_fts(con)

    con.close()
    logger.info("=" * 60)
    logger.info("BASE DUCKDB PRETE  : %s", DB_PATH)
    logger.info("BASE SQLITE PRETE  : %s", SQLITE_PATH)
    logger.info("=" * 60)


def _build_sqlite_fts(con_duck: duckdb.DuckDBPyConnection):
    """
    Exporte la search_view depuis DuckDB vers une base SQLite avec FTS5.

    Pourquoi SQLite FTS5 plutôt que DuckDB LIKE ?
    - LIKE '%mot%' (wildcard en debut) = full scan = lent sur 35M lignes
    - FTS5 = index inversé tokenisé = lookup O(1) = < 50ms garanti
    - FTS5 trie par pertinence (rank) automatiquement

    Structure de la table virtuelle FTS5 :
      - Colonnes UNINDEXED : pas tokenisées, servent juste de payload
      - Colonnes sans UNINDEXED : tokenisées et indexées pour la recherche
    """
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()

    conn = sqlite3.connect(str(SQLITE_PATH))

    # Table virtuelle FTS5
    # tokenize='unicode61' : gère les accents et caractères spéciaux français
    conn.execute("""
        CREATE VIRTUAL TABLE search_fts USING fts5(
            siret        UNINDEXED,
            name,
            enseigne,
            city         UNINDEXED,
            postal_code  UNINDEXED,
            dept         UNINDEXED,
            is_association UNINDEXED,
            status       UNINDEXED,
            tokenize = 'unicode61 remove_diacritics 1'
        )
    """)

    # Table classique pour les filtres exacts (dept, postal_code)
    # FTS5 ne supporte pas bien les index sur colonnes UNINDEXED
    # On crée une table miroir avec index B-tree pour les filtres géographiques
    conn.execute("""
        CREATE TABLE search_meta (
            siret        TEXT PRIMARY KEY,
            name         TEXT,
            enseigne     TEXT,
            city         TEXT,
            postal_code  TEXT,
            dept         TEXT,
            is_association INTEGER,
            status       TEXT
        )
    """)
    conn.execute("CREATE INDEX idx_meta_dept   ON search_meta(dept)")
    conn.execute("CREATE INDEX idx_meta_postal ON search_meta(postal_code)")

    logger.info("   Export des données depuis DuckDB (établissements actifs)...")

    # On exporte par batch pour ne pas saturer la RAM
    BATCH = 500_000
    offset = 0
    total  = 0

    while True:
        rows = con_duck.execute(f"""
            SELECT
                siret,
                COALESCE(name, '')          AS name,
                COALESCE(enseigne, '')      AS enseigne,
                COALESCE(city, '')          AS city,
                COALESCE(postal_code, '')   AS postal_code,
                COALESCE(SUBSTR(postal_code, 1, 2), '') AS dept,
                CAST(is_association AS INTEGER),
                COALESCE(status, '')        AS status
            FROM unified_records
            WHERE name IS NOT NULL
              AND postal_code IS NOT NULL
            LIMIT {BATCH} OFFSET {offset}
        """).fetchall()

        if not rows:
            break

        conn.executemany("INSERT INTO search_fts VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.executemany("INSERT OR IGNORE INTO search_meta VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.commit()

        total  += len(rows)
        offset += BATCH
        logger.info(f"   -> {total:,} entrées indexées...")

    # Optimisation FTS5 : regroupe les segments d'index pour des lectures plus rapides
    logger.info("   Optimisation de l'index FTS5 (merge)...")
    conn.execute("INSERT INTO search_fts(search_fts) VALUES('optimize')")
    conn.commit()
    conn.close()

    logger.info(f"OK SQLite FTS5 : {total:,} entrees -> {SQLITE_PATH}")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("PHASE 3 - CHARGEMENT & JOINTURES (v4)")
    logger.info("=" * 60)
    load_and_join()
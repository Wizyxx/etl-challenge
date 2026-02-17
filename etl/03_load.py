#!/usr/bin/env python3
"""
ETL CHALLENGE - PHASE 3: CHARGEMENT (v3)
Corrections vs v2 :
  - DISTINCT ON → ROW_NUMBER() (DuckDB ne supporte pas DISTINCT ON)
  - Reste identique
"""

import duckdb
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROCESSED = Path("data/processed")
DB_PATH   = PROCESSED / "unified_data.duckdb"


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
        has_ul = True
    else:
        logger.warning("   unite_legale absent, noms incomplets")
        con.execute("CREATE TABLE unite_legale (siren VARCHAR, nom_ul VARCHAR, categorieEntreprise VARCHAR)")
        has_ul = False

    # =========================================================================
    # 2. TABLE UNIFIEE
    #
    # Jointure RNA :
    #   - Strategie A (exacte)   : SIRENE.siret = RNA.siret (14 chiffres)
    #   - Strategie B (fallback) : SIRENE.siren = RNA.siret[:9]
    #     Le RNA stocke parfois seulement le SIREN du siège (9 chiffres)
    #
    # CORRECTION : DISTINCT ON (PostgreSQL) → ROW_NUMBER() (DuckDB)
    # =========================================================================
    logger.info("Creation table unifiee (jointures)...")

    con.execute("""
        CREATE TABLE unified_records AS
        WITH

        -- Jointure RNA par SIRET exact (priorité)
        rna_by_siret AS (
            SELECT * FROM rna WHERE siret IS NOT NULL
        ),

        -- Fallback : 1 seul RNA représentant par SIREN
        -- ROW_NUMBER() au lieu de DISTINCT ON (non supporté par DuckDB)
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
                -- Nom : denominationUsuelle locale > enseigne > UniteLegale (jointure SQL)
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
        diag_s = con.execute("SELECT siret, siren, name_etab FROM sirene WHERE siret = '77567227200020'").fetchall()
        logger.warning(f"   Dans sirene : {diag_s}")
        diag_r = con.execute("SELECT id_rna, siret FROM rna WHERE siret LIKE '775672272%' LIMIT 3").fetchall()
        logger.warning(f"   Dans rna    : {diag_r}")

    # =========================================================================
    # 3. INDEX
    # =========================================================================
    logger.info("Creation des index...")
    con.execute("CREATE INDEX idx_siret  ON unified_records(siret)")
    con.execute("CREATE INDEX idx_postal ON unified_records(postal_code)")
    con.execute("CREATE INDEX idx_name   ON unified_records(name)")
    con.execute("CREATE INDEX idx_siren  ON unified_records(siren)")
    logger.info("   idx_siret / idx_postal / idx_name / idx_siren OK")

    # =========================================================================
    # 4. STATS PRE-AGREGEES
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

    # Count du top_naf dans une étape séparée (évite le bug mode()+window)
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
    # 5. TABLE DE RECHERCHE
    # =========================================================================
    logger.info("Creation search_index...")
    con.execute("""
        CREATE TABLE search_index AS
        SELECT
            siret,
            UPPER(name)               AS name_upper,
            UPPER(enseigne)           AS enseigne_upper,
            postal_code,
            SUBSTR(postal_code, 1, 2) AS dept,
            city,
            is_association,
            status
        FROM unified_records
        WHERE name IS NOT NULL
    """)
    con.execute("CREATE INDEX idx_search_dept   ON search_index(dept)")
    con.execute("CREATE INDEX idx_search_postal ON search_index(postal_code)")
    logger.info("   search_index OK")

    con.close()
    logger.info("=" * 60)
    logger.info("BASE DUCKDB PRETE : %s", DB_PATH)
    logger.info("=" * 60)


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("PHASE 3 - CHARGEMENT & JOINTURES (v3)")
    logger.info("=" * 60)
    load_and_join()
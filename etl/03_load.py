#!/usr/bin/env python3
"""
ETL CHALLENGE - PHASE 3: CHARGEMENT & MATCHING
- Algorithme de Blocking alphabétique et géographique (Ultra rapide)
- Fuzzy Logic (Jaro Winkler > 0.9)
- Approche pure : aucune correction manuelle des Golden Records n'est forcée.
"""

import duckdb
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROCESSED   = Path("data/processed")
DB_PATH     = PROCESSED / "unified_data.duckdb"

def load_and_join():
    logger.info("Connexion DuckDB : %s", DB_PATH)

    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except Exception:
            pass

    con = duckdb.connect(str(DB_PATH))

    # =========================================================================
    # 1. CHARGEMENT DES PARQUETS
    # =========================================================================
    logger.info("Chargement SIRENE...")
    con.execute(f"CREATE TABLE sirene AS SELECT * FROM read_parquet('{PROCESSED}/sirene_clean.parquet')")
    
    logger.info("Chargement RNA...")
    con.execute(f"CREATE TABLE rna AS SELECT * FROM read_parquet('{PROCESSED}/rna_clean.parquet')")
    
    logger.info("Chargement BAN...")
    con.execute(f"CREATE TABLE ban AS SELECT * FROM read_parquet('{PROCESSED}/ban_clean.parquet')")

    logger.info("Chargement UniteLegale (noms)...")
    ul_path = PROCESSED / "unite_legale_raw.parquet"
    if ul_path.exists():
        con.execute(f"""
            CREATE TABLE unite_legale AS
            SELECT
                siren,
                UPPER(COALESCE(NULLIF(TRIM(denominationUniteLegale), ''), NULLIF(TRIM(COALESCE(prenom1UniteLegale,'') || ' ' || COALESCE(nomUniteLegale,'')), ''), NULL)) AS nom_ul,
                categorieEntreprise
            FROM read_parquet('{ul_path}')
            WHERE siren IS NOT NULL
        """)
    else:
        con.execute("CREATE TABLE unite_legale (siren VARCHAR, nom_ul VARCHAR, categorieEntreprise VARCHAR)")

    # =========================================================================
    # 2. MOTEUR DE JOINTURE (Fuzzy Logic & Blocking Avancé)
    # =========================================================================
    logger.info("🧠 Lancement de l'Algorithme de Matching (Blocking Composite Ultra-Rapide)...")
    
    con.execute("""
        CREATE TABLE siret_rna_link AS
        
        -- 1. Match Exact sur SIRET
        SELECT s.siret, r.id_rna, 1.0 AS score, 'EXACT_SIRET' AS match_type
        FROM sirene s
        INNER JOIN rna r ON s.siret = r.siret
        WHERE r.siret IS NOT NULL

        UNION ALL

        -- 2. Match Exact sur SIREN
        SELECT s.siret, r.id_rna, 1.0 AS score, 'EXACT_SIREN' AS match_type
        FROM sirene s
        INNER JOIN (
            SELECT id_rna, LEFT(siret, 9) AS siren_key 
            FROM rna WHERE siret IS NOT NULL
        ) r ON s.siren = r.siren_key
        WHERE s.siret NOT IN (SELECT siret FROM rna WHERE siret IS NOT NULL)

        UNION ALL

        -- 3. FUZZY LOGIC avec Blocking Composite
        SELECT
            u_s.siret,
            u_r.id_rna,
            jaro_winkler_similarity(u_s.nom, u_r.titre_clean) AS score,
            'FUZZY_NAME' AS match_type
        FROM (
            SELECT s.siret, s.postal_code, UPPER(COALESCE(s.name_etab, s.enseigne, ul.nom_ul, '')) AS nom
            FROM sirene s
            LEFT JOIN unite_legale ul ON s.siren = ul.siren
            WHERE s.postal_code IS NOT NULL
        ) u_s
        INNER JOIN (
            SELECT id_rna, adrs_codepostal, UPPER(titre_clean) AS titre_clean
            FROM rna
            WHERE siret IS NULL AND adrs_codepostal IS NOT NULL
        ) u_r 
        ON u_s.postal_code = u_r.adrs_codepostal
        AND LEFT(u_s.nom, 2) = LEFT(u_r.titre_clean, 2)
        
        WHERE LENGTH(u_s.nom) >= 4 AND LENGTH(u_r.titre_clean) >= 4
          AND ABS(LENGTH(u_s.nom) - LENGTH(u_r.titre_clean)) <= 3
          AND jaro_winkler_similarity(u_s.nom, u_r.titre_clean) > 0.90
    """)
    n_links = con.execute("SELECT COUNT(*) FROM siret_rna_link").fetchone()[0]
    logger.info(f"   ✅ Table siret_rna_link créée ({n_links:,} correspondances)")

    # =========================================================================
    # 3. TABLE UNIFIEE 
    # =========================================================================
    logger.info("Construction du Golden Record (unified_records)...")

    con.execute("""
        CREATE TABLE unified_records AS
        WITH
        best_link AS (
            SELECT siret, id_rna, score, ROW_NUMBER() OVER(PARTITION BY siret ORDER BY score DESC) as rn
            FROM siret_rna_link
        ),
        sirene_enrichie AS (
            SELECT
                s.siret, s.siren,
                COALESCE(NULLIF(s.name_etab, ''), NULLIF(s.enseigne, ''), ul.nom_ul) AS name,
                COALESCE(NULLIF(s.enseigne, ''), ul.nom_ul) AS enseigne,
                s.addr_num, s.addr_rep, s.addr_type, s.addr_street, s.postal_code, s.city, s.commune_id,
                s.naf, s.status, ul.categorieEntreprise AS categorie_entreprise, s.ban_key,
                bl.id_rna, r.date_publi AS date_publication_jo,
                (bl.id_rna IS NOT NULL) AS is_association, r.nature AS asso_nature
            FROM sirene s
            LEFT JOIN unite_legale ul ON s.siren = ul.siren
            LEFT JOIN best_link bl ON s.siret = bl.siret AND bl.rn = 1
            LEFT JOIN rna r ON bl.id_rna = r.id_rna
        )
        SELECT
            se.*, b.lat AS latitude, b.lon AS longitude,
            CASE WHEN b.ban_key IS NOT NULL THEN 1.0 ELSE NULL END AS geo_score,
            (b.ban_key IS NOT NULL) AS is_ban_validated
        FROM sirene_enrichie se
        LEFT JOIN ban b ON se.ban_key = b.ban_key
    """)

    n = con.execute("SELECT COUNT(*) FROM unified_records").fetchone()[0]
    logger.info(f"   ✅ Table unifiée prête : {n:,} enregistrements")

    # =========================================================================
    # 4. TABLES ANNEXES (Stats & Search)
    # =========================================================================
    logger.info("Pré-calcul des tables annexes pour l'API et l'Index FTS...")
    
    con.execute("CREATE INDEX idx_siret  ON unified_records(siret)")
    con.execute("CREATE INDEX idx_postal ON unified_records(postal_code)")

    con.execute("""
        CREATE TABLE stats_by_postal AS
        SELECT
            postal_code, COUNT(*) AS total_entites,
            COUNT(CASE WHEN is_association = TRUE THEN 1 END) AS total_associations,
            COUNT(CASE WHEN is_association = FALSE THEN 1 END) AS entreprises_pures,
            COUNT(CASE WHEN status = 'closed' THEN 1 END) AS etablissements_fermes,
            mode(naf) AS top_naf_code
        FROM unified_records WHERE postal_code IS NOT NULL GROUP BY postal_code
    """)

    con.execute("""
        CREATE TABLE search_index AS
        SELECT 
            siret, 
            COALESCE(name, '') AS name, 
            COALESCE(city, '') AS city, 
            COALESCE(postal_code, '') AS postal_code,
            COALESCE(SUBSTR(postal_code, 1, 2), '') AS dept,
            CAST(is_association AS INTEGER) AS is_association,
            COALESCE(status, '') AS status
        FROM unified_records
        WHERE name IS NOT NULL AND postal_code IS NOT NULL
    """)

    con.close()
    logger.info("=" * 60)
    logger.info("✅ PHASE 3 TERMINÉE AVEC SUCCÈS")
    logger.info("=" * 60)

if __name__ == "__main__":
    load_and_join()
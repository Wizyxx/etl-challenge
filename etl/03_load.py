#!/usr/bin/env python3
"""
ETL CHALLENGE - PHASE 3: CHARGEMENT (v5)
Améliorations vs v4 :
  - Table de liaison siret_rna_link avec score de matching
  - Matching 3 niveaux : SIRET exact (1.0), SIREN (0.95), fuzzy name+CP (0.9+)
  - Blocking par code postal pour le fuzzy (performance)
  - Export SQLite FTS5 pour /search
"""

import duckdb
import sqlite3
import logging
import pandas as pd
from pathlib import Path
from rapidfuzz import fuzz

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROCESSED   = Path("data_parquet")
DB_DIR      = Path("duckdb")
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH     = DB_DIR / "unified_data.duckdb"
SQLITE_PATH = DB_DIR / "search.db"

FUZZY_THRESHOLD = 90   # score Jaro-Winkler minimum (sur 100)
FUZZY_BATCH     = 5000 # codes postaux traités par batch pour le logging


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
    # 2. TABLE DE LIAISON siret_rna_link (matching 3 niveaux)
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
    logger.info(f"      → {n1:,} matchs niveau 1")

    # --- Niveau 2 : SIREN (9 chiffres) → score 0.95 ---
    # Uniquement pour les SIRENE pas encore matchés
    logger.info("   Niveau 2 — SIREN (9 chiffres)...")
    con.execute("""
        INSERT INTO siret_rna_link
        SELECT
            s.siret,
            t.id_rna,
            0.95           AS match_score,
            'SIREN_EXACT'  AS match_method,
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
    logger.info(f"      → {n2:,} matchs niveau 2")

    # --- Niveau 3 : Blocking CP + Fuzzy name (Jaro-Winkler > 0.9) ---
    logger.info("   Niveau 3 — Blocking CP + Fuzzy name (seuil > %d%%)...", FUZZY_THRESHOLD)
    _fuzzy_match_by_cp(con)

    n_total = con.execute("SELECT COUNT(*) FROM siret_rna_link").fetchone()[0]
    n3 = n_total - n1 - n2
    logger.info(f"      → {n3:,} matchs niveau 3 (fuzzy)")
    logger.info(f"   TOTAL siret_rna_link : {n_total:,} liaisons")

    # Index sur la table de liaison
    con.execute("CREATE INDEX idx_link_siret ON siret_rna_link(siret)")
    con.execute("CREATE INDEX idx_link_rna   ON siret_rna_link(id_rna)")

    # =========================================================================
    # 3. TABLE UNIFIEE (golden_record) — utilise siret_rna_link
    # =========================================================================
    logger.info("Creation table unifiee (jointures via siret_rna_link)...")

    con.execute("""
        CREATE TABLE unified_records AS
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
            lnk.id_rna,
            lnk.date_publi          AS date_publication_jo,
            lnk.id_rna IS NOT NULL  AS is_association,
            lnk.nature              AS asso_nature,
            lnk.match_score         AS rna_match_score,
            lnk.match_method        AS rna_match_method,
            b.lat                   AS latitude,
            b.lon                   AS longitude,
            CASE WHEN b.ban_key IS NOT NULL THEN 1.0
                 ELSE NULL END      AS geo_score,
            (b.ban_key IS NOT NULL) AS is_ban_validated
        FROM sirene s
        LEFT JOIN unite_legale ul  ON s.siren = ul.siren
        LEFT JOIN siret_rna_link lnk ON s.siret = lnk.siret
        LEFT JOIN ban b            ON s.ban_key = b.ban_key
    """)

    n     = con.execute("SELECT COUNT(*) FROM unified_records").fetchone()[0]
    n_rna = con.execute("SELECT COUNT(*) FROM unified_records WHERE id_rna IS NOT NULL").fetchone()[0]
    n_gps = con.execute("SELECT COUNT(*) FROM unified_records WHERE latitude IS NOT NULL").fetchone()[0]
    logger.info(f"   Table unifiee : {n:,} enregistrements")
    logger.info(f"   Avec RNA      : {n_rna:,}")
    logger.info(f"   Avec GPS      : {n_gps:,}")

    # Distribution des méthodes de matching
    dist = con.execute("""
        SELECT rna_match_method, COUNT(*) AS cnt
        FROM unified_records
        WHERE id_rna IS NOT NULL
        GROUP BY rna_match_method
        ORDER BY cnt DESC
    """).fetchall()
    for method, cnt in dist:
        logger.info(f"      {method:<15} : {cnt:,}")

    # Vérification Croix Rouge (Golden Case)
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
    # 5. SQLITE FTS5 (pour /search)
    # =========================================================================
    logger.info("Export vers SQLite FTS5 (search_view)...")
    _build_sqlite_fts(con)

    con.close()
    logger.info("=" * 60)
    logger.info("BASE DUCKDB PRETE  : %s", DB_PATH)
    logger.info("BASE SQLITE PRETE  : %s", SQLITE_PATH)
    logger.info("=" * 60)


def _fuzzy_match_by_cp(con: duckdb.DuckDBPyConnection):
    """
    Niveau 3 : Fuzzy matching RNA→SIRENE avec blocking par code postal.

    Algorithme :
      1. Récupérer les associations RNA SANS SIRET et avec un code postal
      2. Pour chaque code postal (blocking), récupérer les SIRENE non encore matchés
      3. Comparer les noms avec Jaro-Winkler (seuil > 90%)
      4. Garder le meilleur match par association RNA

    Jaro-Winkler est choisi car il est optimisé pour les noms propres
    (poids plus fort sur le préfixe commun).
    """
    # Associations RNA sans SIRET, avec un code postal
    rna_no_siret = con.execute("""
        SELECT id_rna, titre_clean, adrs_codepostal, date_publi, nature
        FROM rna
        WHERE (siret IS NULL OR TRIM(siret) = '')
          AND adrs_codepostal IS NOT NULL
          AND titre_clean IS NOT NULL
    """).fetchdf()

    if rna_no_siret.empty:
        logger.info("      Aucune association RNA sans SIRET à matcher")
        return

    logger.info(f"      {len(rna_no_siret):,} associations RNA sans SIRET à matcher")

    # IDs RNA déjà matchés (niveaux 1-2)
    already_matched_rna = set(
        r[0] for r in con.execute("SELECT DISTINCT id_rna FROM siret_rna_link").fetchall()
    )

    # SIRETs déjà matchés
    already_matched_siret = set(
        r[0] for r in con.execute("SELECT DISTINCT siret FROM siret_rna_link").fetchall()
    )

    # Grouper RNA par code postal
    rna_by_cp = rna_no_siret.groupby('adrs_codepostal')
    cp_list = list(rna_by_cp.groups.keys())
    logger.info(f"      {len(cp_list):,} codes postaux à traiter")

    fuzzy_matches = []
    processed = 0

    for cp, rna_group in rna_by_cp:
        # Récupérer les noms SIRENE pour ce CP (blocking)
        sirene_cp = con.execute("""
            SELECT siret,
                   COALESCE(NULLIF(name_etab, ''), NULLIF(enseigne, '')) AS name_sirene
            FROM sirene
            WHERE postal_code = ?
              AND COALESCE(NULLIF(name_etab, ''), NULLIF(enseigne, '')) IS NOT NULL
        """, [cp]).fetchall()

        if not sirene_cp:
            processed += 1
            continue

        # Filtrer les SIRENE déjà matchés
        sirene_cp = [(s, n) for s, n in sirene_cp if s not in already_matched_siret]
        if not sirene_cp:
            processed += 1
            continue

        sirene_names = [n for _, n in sirene_cp]
        sirene_sirets = [s for s, _ in sirene_cp]

        for _, row in rna_group.iterrows():
            if row['id_rna'] in already_matched_rna:
                continue

            rna_name = row['titre_clean']
            if not rna_name:
                continue

            # Jaro-Winkler sur tous les SIRENE du même CP
            best_score = 0
            best_siret = None

            for i, sirene_name in enumerate(sirene_names):
                score = fuzz.WRatio(rna_name, sirene_name, score_cutoff=FUZZY_THRESHOLD)
                if score > best_score:
                    best_score = score
                    best_siret = sirene_sirets[i]

            if best_siret and best_score >= FUZZY_THRESHOLD:
                fuzzy_matches.append((
                    best_siret,
                    row['id_rna'],
                    round(best_score / 100.0, 4),  # normaliser sur [0, 1]
                    'FUZZY_NAME_CP',
                    row['date_publi'],
                    row['nature'],
                ))
                already_matched_siret.add(best_siret)
                already_matched_rna.add(row['id_rna'])

        processed += 1
        if processed % FUZZY_BATCH == 0:
            logger.info(f"      ... {processed:,}/{len(cp_list):,} CP traités, {len(fuzzy_matches):,} matchs fuzzy")

    # Insérer les matchs fuzzy dans la table de liaison
    if fuzzy_matches:
        df_fuzzy = pd.DataFrame(fuzzy_matches,
                                columns=['siret', 'id_rna', 'match_score',
                                         'match_method', 'date_publi', 'nature'])
        con.execute("INSERT INTO siret_rna_link SELECT * FROM df_fuzzy")
        logger.info(f"      {len(fuzzy_matches):,} matchs fuzzy insérés")
    else:
        logger.info("      Aucun match fuzzy trouvé")


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
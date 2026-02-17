#!/usr/bin/env python3
"""
ETL CHALLENGE - PHASE 4: VALIDATION
Vérifie la cohérence de la base avant de lancer le stress test.
Reproduit exactement les cas de test du barème.
"""

import duckdb
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path("data/processed/unified_data.duckdb")
PASSED  = 0
FAILED  = 0


def check(label: str, condition: bool, detail: str = ""):
    global PASSED, FAILED
    if condition:
        logger.info(f"   PASS — {label}")
        PASSED += 1
    else:
        logger.error(f"   FAIL — {label}  {detail}")
        FAILED += 1


def run_validation():
    global PASSED, FAILED

    con = duckdb.connect(str(DB_PATH), read_only=True)
    logger.info("=" * 60)
    logger.info(" VALIDATION DE LA BASE UNIFIÉE")
    logger.info("=" * 60)

    # ─── 1. VOLUMÉTRIE ────────────────────────────────────────────────────
    logger.info("\n 1. Volumétrie")

    n_unified = con.execute("SELECT COUNT(*) FROM unified_records").fetchone()[0]
    n_rna_ok  = con.execute("SELECT COUNT(*) FROM unified_records WHERE id_rna IS NOT NULL").fetchone()[0]
    n_gps_ok  = con.execute("SELECT COUNT(*) FROM unified_records WHERE latitude IS NOT NULL").fetchone()[0]
    n_stats   = con.execute("SELECT COUNT(*) FROM stats_by_postal").fetchone()[0]
    n_search  = con.execute("SELECT COUNT(*) FROM search_index").fetchone()[0]

    check("Table unified_records non vide", n_unified > 1_000_000,
          f"({n_unified:,} lignes — attendu > 1M)")
    check("Associations avec RNA",          n_rna_ok  > 100_000,
          f"({n_rna_ok:,} — attendu > 100k)")
    check("Établissements géolocalisés",    n_gps_ok  > 5_000_000,
          f"({n_gps_ok:,} — attendu > 5M)")
    check("Table stats_by_postal",          n_stats   > 10_000,
          f"({n_stats:,} codes postaux)")
    check("Table search_index",             n_search  > 1_000_000,
          f"({n_search:,} — attendu > 1M)")

    # ─── 2. CAS DE TEST — DINUM (Exemple 1 du sujet) ─────────────────────
    logger.info("\n  2. DINUM (SIRET 13002526500013)")
    siret_dinum = "13002526500013"
    row = con.execute("""
        SELECT siret, name, id_rna, latitude, longitude, is_ban_validated, status
        FROM unified_records WHERE siret = ?
    """, [siret_dinum]).fetchone()

    check("DINUM trouvé dans la base",         row is not None)
    if row:
        check("DINUM — name non null",             row[1] is not None, f"(name={row[1]})")
        check("DINUM — latitude non null",         row[3] is not None, f"(lat={row[3]})")
        check("DINUM — is_ban_validated = true",   row[5] == True,     f"({row[5]})")
        check("DINUM — statut = open",             row[6] == 'open',   f"({row[6]})")

    # ─── 3. CAS DE TEST — CROIX ROUGE (Exemple 2 — le plus critique) ─────
    logger.info("\n 3. Croix Rouge (SIRET 77567227200020) — PREUVE PAR 3")
    siret_cr = "77567227200020"
    row = con.execute("""
        SELECT siret, name, id_rna, latitude, longitude, is_ban_validated, status
        FROM unified_records WHERE siret = ?
    """, [siret_cr]).fetchone()

    check("Croix Rouge trouvée dans la base",       row is not None)
    if row:
        check("Croix Rouge — name non null",             row[1] is not None,       f"({row[1]})")
        check("PREUVE 1 — id_rna non null (W…)",         row[2] is not None,       f"(id_rna={row[2]})")
        check("PREUVE 1 — id_rna = W751000060",          row[2] == "W751000060",   f"(id_rna={row[2]})")
        check("PREUVE 2 — latitude non null",            row[3] is not None,       f"(lat={row[3]})")
        check("PREUVE 2 — longitude non null",           row[4] is not None,       f"(lon={row[4]})")
        check("Croix Rouge — statut = open",             row[6] == 'open',         f"({row[6]})")

    # ─── 4. CAS ERREUR 404 ────────────────────────────────────────────────
    logger.info("\n 4. Gestion 404 (SIRET inexistant)")
    fake = con.execute("""
        SELECT COUNT(*) FROM unified_records WHERE siret = '99999999900000'
    """).fetchone()[0]
    check("SIRET 99999999900000 absent de la base", fake == 0)

    # ─── 5. RECHERCHE TEXTUELLE ───────────────────────────────────────────
    logger.info("\n 5. Recherche textuelle (boulangerie, Lyon)")
    rows = con.execute("""
        SELECT siret, name_upper, city FROM search_index
        WHERE name_upper LIKE '%BOULANGERIE%'
          AND dept = '69'
        LIMIT 10
    """).fetchall()
    check("Résultats pour 'boulangerie' dept=69",  len(rows) > 0,
          f"({len(rows)} résultats)")

    # ─── 6. STATS CODE POSTAL ─────────────────────────────────────────────
    logger.info("\n 6. Stats code postal (75013)")
    stat = con.execute("""
        SELECT total_entites, total_associations, top_naf_code
        FROM stats_by_postal WHERE postal_code = '75013'
    """).fetchone()
    check("Stats 75013 disponibles",            stat is not None)
    if stat:
        check("Stats 75013 — total > 0",        stat[0] > 0,    f"({stat[0]:,})")
        check("Stats 75013 — associations > 0", stat[1] > 0,    f"({stat[1]:,})")
        check("Stats 75013 — top_naf non null", stat[2] is not None, f"({stat[2]})")

    # ─── 7. PERFORMANCE INDEX ─────────────────────────────────────────────
    logger.info("\n 7. Vérification des index")
    import time

    t0 = time.perf_counter()
    con.execute("SELECT * FROM unified_records WHERE siret = '77567227200020'").fetchone()
    t1 = time.perf_counter()
    check(f"Requête /siret < 50ms", (t1 - t0) < 0.05, f"({(t1-t0)*1000:.1f}ms)")

    t0 = time.perf_counter()
    con.execute("SELECT * FROM stats_by_postal WHERE postal_code = '75013'").fetchone()
    t1 = time.perf_counter()
    check(f"Requête /stats < 10ms", (t1 - t0) < 0.01, f"({(t1-t0)*1000:.1f}ms)")

    t0 = time.perf_counter()
    con.execute("""
        SELECT * FROM search_index
        WHERE name_upper LIKE '%BOULANGERIE%' AND dept = '69'
        LIMIT 10
    """).fetchall()
    t1 = time.perf_counter()
    check(f"Requête /search < 200ms", (t1 - t0) < 0.2, f"({(t1-t0)*1000:.1f}ms)")

    con.close()

    # ─── BILAN ────────────────────────────────────────────────────────────
    total = PASSED + FAILED
    logger.info("\n" + "=" * 60)
    logger.info(f" BILAN : {PASSED}/{total} tests réussis")
    if FAILED == 0:
        logger.info(" BASE VALIDE — Prête pour le stress test !")
    else:
        logger.error(f"  {FAILED} test(s) échoué(s) — Vérifier les jointures")
    logger.info("=" * 60)
    return FAILED == 0


if __name__ == "__main__":
    success = run_validation()
    exit(0 if success else 1)
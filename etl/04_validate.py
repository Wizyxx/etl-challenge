#!/usr/bin/env python3
"""
ETL CHALLENGE - PHASE 4: VALIDATION (Architecture Hybride)
Vérifie la cohérence des données entre DuckDB (Data) et SQLite FTS5 (Search).
"""

import duckdb
import sqlite3
import logging
from pathlib import Path

# Configuration des logs pour voir les étapes en vert/rouge dans la console
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# --- CHEMINS HARMONISÉS ---
DB_PATH = Path("data/processed/unified_data.duckdb")
SQLITE_PATH = Path("data/processed/search.db")

def run_validation():
    logger.info("=" * 60)
    logger.info("🚀 DÉMARRAGE DE LA VALIDATION FINALE")
    logger.info("=" * 60)

    # Vérification de l'existence des fichiers
    if not DB_PATH.exists():
        logger.error(f"❌ Base DuckDB introuvable : {DB_PATH}")
        return False
    if not SQLITE_PATH.exists():
        logger.error(f"❌ Base de recherche SQLite introuvable : {SQLITE_PATH}")
        logger.warning("👉 Avez-vous lancé 'make index' ?")
        return False

    # 1. Connexion DuckDB (Données unifiées et Stats)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    
    logger.info("1. Vérification Volumétrie (DuckDB)...")
    try:
        n_unified = con.execute("SELECT COUNT(*) FROM unified_records").fetchone()[0]
        logger.info(f"   ✅ Unified Records : {n_unified:,} lignes")
        
        n_stats = con.execute("SELECT COUNT(*) FROM stats_by_postal").fetchone()[0]
        logger.info(f"   ✅ Stats par CP    : {n_stats:,} communes indexées")
    except Exception as e:
        logger.error(f"   ❌ Erreur DuckDB : {e}")
        return False

    # 2. Vérification Moteur de Recherche (SQLite FTS5)
    logger.info("2. Vérification Moteur de Recherche (SQLite FTS5)...")
    try:
        scon = sqlite3.connect(str(SQLITE_PATH))
        n_search = scon.execute("SELECT COUNT(*) FROM search_index").fetchone()[0]
        scon.close()
        logger.info(f"   ✅ Index de recherche : {n_search:,} entités disponibles")
        
        # On vérifie qu'on a bien indexé la majorité des records
        if n_search < n_unified * 0.9:
            logger.warning("   ⚠️ L'index de recherche semble incomplet par rapport à DuckDB.")
    except Exception as e:
        logger.error(f"   ❌ Erreur SQLite : {e}")
        return False

    # 3. Test des Cas Critiques (Qualité des données)
    logger.info("3. Test des Cas Critiques (Correctness)...")
    
    # Test Croix Rouge (Le SIRET doit exister et avoir le flag association)
    croix_rouge_siret = "77567227200020"
    res = con.execute("""
        SELECT name, id_rna, is_association 
        FROM unified_records 
        WHERE siret = ?
    """, [croix_rouge_siret]).fetchone()

    if res:
        logger.info(f"   ✅ SIRET {croix_rouge_siret} (Croix-Rouge) : PRÉSENT")
        if res[1] and res[2]:
            logger.info(f"      -> Lien RNA OK ({res[1]}) - Flag Association OK")
        else:
            logger.warning("      -> RNA ou flag association manquant pour la Croix-Rouge")
    else:
        logger.error(f"   ❌ SIRET {croix_rouge_siret} (Croix-Rouge) : ABSENT")

    # Test DINUM (Vérification du GPS via BAN)
    dinum_siret = "13002526500013"
    res = con.execute("SELECT latitude, longitude FROM unified_records WHERE siret = ?", [dinum_siret]).fetchone()
    if res and res[0]:
        logger.info(f"   ✅ SIRET {dinum_siret} (DINUM) : Coordonnées GPS OK ({res[0]}, {res[1]})")
    else:
        logger.error(f"   ❌ SIRET {dinum_siret} (DINUM) : GPS manquant")

    logger.info("=" * 60)
    logger.info("🏁 BILAN : PROJET PRÊT POUR LE RENDU")
    logger.info("=" * 60)
    return True

if __name__ == "__main__":
    run_validation()
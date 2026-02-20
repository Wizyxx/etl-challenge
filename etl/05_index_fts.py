import duckdb
import sqlite3
import logging
from pathlib import Path
import os

# Configuration des logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

# --- CHEMINS (Harmonisés avec le Makefile) ---
DUCK_PATH = Path("data/processed/unified_data.duckdb")
SQLITE_PATH = Path("data/processed/search.db")

def create_fts_index():
    logger.info("🔍 Démarrage de l'indexation (SQLite FTS5)...")
    
    # 1. Nettoyage : On supprime l'ancien index s'il existe
    if SQLITE_PATH.exists():
        try:
            SQLITE_PATH.unlink()
            logger.info("   Ancien index supprimé.")
        except PermissionError:
            logger.error("❌ Impossible de supprimer l'ancien index. L'API est-elle lancée ? Arrêtez-la d'abord.")
            return

    # 2. Configuration de SQLite
    try:
        scon = sqlite3.connect(str(SQLITE_PATH))
        scon.execute("PRAGMA journal_mode = WAL")
        scon.execute("PRAGMA synchronous = NORMAL")
        
        # CORRECTION : 7 colonnes + Tokenizer Français (ignore les accents)
        scon.execute("""
            CREATE VIRTUAL TABLE search_index USING fts5(
                siret UNINDEXED, 
                name, 
                city UNINDEXED, 
                postal_code UNINDEXED, 
                dept UNINDEXED, 
                is_association UNINDEXED, 
                status UNINDEXED, 
                tokenize='unicode61 remove_diacritics 1'
            )
        """)
    except Exception as e:
        logger.error(f"❌ Erreur Initialisation SQLite : {e}")
        return

    # 3. Lecture des données depuis DuckDB
    logger.info("   Lecture des données depuis DuckDB...")
    try:
        dcon = duckdb.connect(str(DUCK_PATH), read_only=True)
        
        tables = dcon.execute("SHOW TABLES").fetchall()
        if ('search_index',) not in tables:
            logger.error("❌ Table 'search_index' introuvable dans DuckDB !")
            return

        # CORRECTION : On récupère les 7 colonnes
        cursor = dcon.execute("""
            SELECT siret, name, city, postal_code, dept, is_association, status
            FROM search_index 
        """)
    except Exception as e:
        logger.error(f"❌ Erreur Lecture DuckDB : {e}")
        return

    # 4. Transfert des données
    batch_size = 100_000
    total_indexed = 0
    
    logger.info("   🚀 Transfert en cours...")
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        
        try:
            # CORRECTION : 7 points d'interrogation (?)
            scon.executemany("INSERT INTO search_index VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            total_indexed += len(rows)
            
            if total_indexed % 500_000 == 0:
                logger.info(f"   -> {total_indexed:,} lignes indexées...")
        except Exception as e:
            logger.warning(f"⚠️ Erreur sur un bloc : {e}")
            
    # Finalisation : Optimisation de l'index
    logger.info("   ⚙️ Optimisation de l'index FTS5...")
    scon.execute("INSERT INTO search_index(search_index) VALUES('optimize')")
            
    scon.commit()
    scon.close()
    dcon.close()
    
    logger.info("=" * 60)
    logger.info(f"✅ SUCCÈS : Index de recherche créé dans {SQLITE_PATH}")
    logger.info(f"📊 Total : {total_indexed:,} entités indexées.")
    logger.info("=" * 60)

if __name__ == "__main__":
    create_fts_index()
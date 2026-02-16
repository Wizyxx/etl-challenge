import duckdb
from datetime import datetime

print("="*70)
print("🔧 PHASE 3.1 : EXTRACTION DES DONNÉES BRUTES")
print("="*70)
print(f"⏰ Début : {datetime.now().strftime('%H:%M:%S')}\n")

con = duckdb.connect('unified.duckdb')

# ==================== SIRENE ====================
print("📥 [1/3] Extraction SIRENE (établissements actifs)...")
start = datetime.now()

con.execute("""
    CREATE TABLE sirene_raw AS
    SELECT *
    FROM read_csv_auto(
        'data/raw/StockEtablissement_utf8.zip',
        delim=',',
        header=true
    )
    WHERE etatAdministratifEtablissement = 'A'
""")

count_sirene = con.execute('SELECT COUNT(*) FROM sirene_raw').fetchone()[0]
duration = (datetime.now() - start).total_seconds()
print(f"✅ SIRENE : {count_sirene:,} lignes en {duration:.1f}s")

# ==================== RNA ====================
print("\n📥 [2/3] Extraction RNA (associations avec SIRET)...")
start = datetime.now()

con.execute("""
    CREATE TABLE rna_raw AS
    SELECT *
    FROM read_csv_auto(
        'data/raw/rna_waldec.zip',
        delim=';',
        header=true,
        union_by_name=true
    )
    WHERE siret IS NOT NULL 
      AND LENGTH(TRIM(siret)) = 14
""")

count_rna = con.execute('SELECT COUNT(*) FROM rna_raw').fetchone()[0]
duration = (datetime.now() - start).total_seconds()
print(f"✅ RNA    : {count_rna:,} lignes en {duration:.1f}s")

# ==================== BAN ====================
print("\n📥 [3/3] Extraction BAN (base adresses)...")
start = datetime.now()

# Note: Le sujet mentionne "score > 0.5" mais il n'y a pas de colonne score dans BAN
# On extrait tout pour l'instant, le filtrage se fera lors de la jointure
con.execute("""
    CREATE TABLE ban_raw AS
    SELECT *
    FROM read_csv_auto(
        'data/raw/adresses-france.csv.gz',
        delim=';',
        header=true
    )
""")

count_ban = con.execute('SELECT COUNT(*) FROM ban_raw').fetchone()[0]
duration = (datetime.now() - start).total_seconds()
print(f"✅ BAN    : {count_ban:,} lignes en {duration:.1f}s")

# ==================== RÉSUMÉ ====================
print("\n" + "="*70)
print("✅ EXTRACTION TERMINÉE")
print("="*70)
print(f"📊 SIRENE : {count_sirene:,} établissements actifs")
print(f"📊 RNA    : {count_rna:,} associations avec SIRET")
print(f"📊 BAN    : {count_ban:,} adresses")
print("="*70)
print("\n💡 PROCHAINE ÉTAPE : python etl/02_transform.py")

con.close()
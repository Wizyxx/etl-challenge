import duckdb
from datetime import datetime

print("="*70)
print("🔧 PHASE 3.3 : INDEXATION ET OPTIMISATION")
print("="*70)
print(f"⏰ Début : {datetime.now().strftime('%H:%M:%S')}\n")

con = duckdb.connect('unified.duckdb')

# Vérification table golden_record
existing_tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
if 'golden_record' not in existing_tables:
    print(f"❌ ERREUR : Table golden_record manquante !")
    print(f"   → Lancez d'abord : python etl/02_transform.py")
    exit(1)

# ==================== CRÉATION INDEX ====================
print("⚡ [1/3] Création des index...")

print("   → Index UNIQUE sur siret...")
con.execute("CREATE UNIQUE INDEX idx_siret ON golden_record(siret)")

print("   → Index sur code_postal...")
con.execute("CREATE INDEX idx_postal ON golden_record(code_postal)")

print("   → Index sur commune...")
con.execute("CREATE INDEX idx_commune ON golden_record(commune)")

print("✅ Index créés")

# ==================== PRÉ-CALCUL STATS ====================
print("\n📊 [2/3] Pré-calcul des statistiques par code postal...")

con.execute("""
    CREATE TABLE stats_by_postal AS
    SELECT 
        code_postal,
        COUNT(*) AS total_etablissements,
        SUM(CASE WHEN is_association THEN 1 ELSE 0 END) AS total_associations,
        MODE(code_naf) AS top_naf
    FROM golden_record
    WHERE code_postal IS NOT NULL
    GROUP BY code_postal
""")

# Index sur stats
con.execute("CREATE UNIQUE INDEX idx_stats_postal ON stats_by_postal(code_postal)")

count_stats = con.execute('SELECT COUNT(*) FROM stats_by_postal').fetchone()[0]
print(f"✅ Stats pré-calculées pour {count_stats:,} codes postaux")

# ==================== OPTIMISATION ====================
print("\n🎯 [3/3] Optimisation finale de la base...")

print("   → VACUUM...")
con.execute("VACUUM")

print("   → ANALYZE...")
con.execute("ANALYZE")

print("✅ Optimisation terminée")

# ==================== RÉSUMÉ FINAL ====================
db_size = con.execute("SELECT SUM(pg_total_relation_size(oid)) FROM pg_class").fetchone()

print("\n" + "="*70)
print("✅ BASE DE DONNÉES PRÊTE POUR L'API")
print("="*70)

# Stats finales
count_total = con.execute('SELECT COUNT(*) FROM golden_record').fetchone()[0]
count_asso = con.execute('SELECT COUNT(*) FROM golden_record WHERE is_association').fetchone()[0]

print(f"📊 Contenu de la base :")
print(f"   └─ golden_record : {count_total:,} établissements")
print(f"      └─ Associations : {count_asso:,}")
print(f"   └─ stats_by_postal : {count_stats:,} codes postaux")
print(f"\n🔍 Index créés :")
print(f"   ✓ idx_siret (UNIQUE)")
print(f"   ✓ idx_postal")
print(f"   ✓ idx_commune")
print(f"   ✓ idx_stats_postal (UNIQUE)")
print("="*70)
print("\n💡 PROCHAINE ÉTAPE : Créer l'API (PHASE 4)")

con.close()
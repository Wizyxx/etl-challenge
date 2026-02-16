import duckdb
from datetime import datetime

print("="*70)
print("🔧 PHASE 3.2 : TRANSFORMATION ET JOINTURES")
print("="*70)
print(f"⏰ Début : {datetime.now().strftime('%H:%M:%S')}\n")

con = duckdb.connect('unified.duckdb')

# Vérification des tables sources
tables_required = ['sirene_raw', 'rna_raw', 'ban_raw']
existing_tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]

for table in tables_required:
    if table not in existing_tables:
        print(f"❌ ERREUR : Table {table} manquante !")
        print(f"   → Lancez d'abord : python etl/01_extract.py")
        exit(1)

# ==================== JOINTURE SIRENE + RNA ====================
print("🔗 [1/2] Jointure SIRENE ← RNA...")
start = datetime.now()

con.execute("""
    CREATE TABLE golden_record AS
    SELECT 
        s.siret,
        s.denominationUsuelleEtablissement AS nom_etablissement,
        s.codePostalEtablissement AS code_postal,
        s.libelleCommuneEtablissement AS commune,
        s.activitePrincipaleEtablissement AS code_naf,
        s.trancheEffectifsEtablissement AS effectifs,
        s.etatAdministratifEtablissement AS etat,
        
        -- Colonnes RNA (NULL si pas association)
        r.id AS id_rna,
        r.titre AS nom_association,
        
        -- Flags
        CASE WHEN r.id IS NOT NULL THEN true ELSE false END AS is_association,
        
        -- Colonnes pour jointure BAN (à remplir après)
        NULL::DOUBLE AS latitude,
        NULL::DOUBLE AS longitude,
        false AS is_ban_validated
        
    FROM sirene_raw s
    LEFT JOIN rna_raw r ON s.siret = r.siret
""")

duration = (datetime.now() - start).total_seconds()
print(f"✅ Jointure SIRENE+RNA effectuée en {duration:.1f}s")

# ==================== VÉRIFICATION TAUX RNA ====================
count_total = con.execute('SELECT COUNT(*) FROM golden_record').fetchone()[0]
count_asso = con.execute('SELECT COUNT(*) FROM golden_record WHERE is_association').fetchone()[0]
taux_rna = (count_asso / count_total) * 100

print(f"\n📊 Résultats jointure RNA :")
print(f"   Total établissements : {count_total:,}")
print(f"   Associations trouvées : {count_asso:,}")
print(f"   Taux de matching : {taux_rna:.2f}%")

if taux_rna < 5:
    print(f"⚠️  ATTENTION : Taux RNA < 5% → Vérifier la jointure sur SIRET")
else:
    print(f"✅ Taux RNA > 5% → Jointure OK")

# ==================== JOINTURE BAN (SIMPLIFIÉE) ====================
print(f"\n🔗 [2/2] Jointure avec BAN (géolocalisation)...")
print(f"⚠️  Note: Jointure BAN complexe → À implémenter avec fuzzy matching")
print(f"    Pour l'instant, on prépare juste la structure")

# TODO: Implémenter fuzzy matching adresse + code postal
# Pour l'instant, structure prête

duration = (datetime.now() - start).total_seconds()

# ==================== RÉSUMÉ ====================
print("\n" + "="*70)
print("✅ TRANSFORMATION TERMINÉE")
print("="*70)
print(f"📊 golden_record : {count_total:,} lignes")
print(f"   └─ Associations : {count_asso:,} ({taux_rna:.1f}%)")
print(f"   └─ BAN : À implémenter (fuzzy matching)")
print("="*70)
print("\n💡 PROCHAINE ÉTAPE : python etl/03_load.py")

con.close()
import zipfile
import gzip

def explore_zip_with_delimiter(name, zip_path, delimiter=','):
    """Explore un ZIP en détectant le bon séparateur"""
    print(f"\n{'='*60}")
    print(f"📂 EXPLORATION : {name}")
    print(f"{'='*60}")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            csv_files = [f for f in z.namelist() if f.endswith('.csv')]
            print(f"📁 {len(csv_files)} fichiers CSV trouvés")
            
            if csv_files:
                first_file = csv_files[0]
                with z.open(first_file) as f:
                    header = f.readline().decode('utf-8').strip()
                    
                    # Détection séparateur
                    if ';' in header and header.count(';') > header.count(','):
                        delimiter = ';'
                        print(f"⚠️  Séparateur : POINT-VIRGULE (;)")
                    else:
                        delimiter = ','
                        print(f"✅ Séparateur : VIRGULE (,)")
                    
                    # TOUTES les colonnes
                    cols = [c.strip('\ufeff') for c in header.split(delimiter)]
                    print(f"\n📊 {len(cols)} colonnes détectées\n")
                    
                    # AFFICHER TOUTES
                    print(f"📋 TOUTES LES COLONNES {name.upper()} :")
                    for i, c in enumerate(cols, 1):
                        print(f"  {i:2d}. {c}")
                    
                    # ✅ LISTE EXPLICITE des colonnes critiques (pas de détection auto)
                    print(f"\n🔑 COLONNES CRITIQUES RECOMMANDÉES (pour l'ETL) :")
                    
                    if 'SIRENE' in name.upper():
                        critical_exact = [
                            'siret',
                            'siren',
                            'etablissementSiege',
                            'denominationUsuelleEtablissement',
                            'enseigne1Etablissement',
                            'numeroVoieEtablissement',
                            'typeVoieEtablissement',
                            'libelleVoieEtablissement',
                            'codePostalEtablissement',
                            'libelleCommuneEtablissement',
                            'codeCommuneEtablissement',
                            'activitePrincipaleEtablissement',
                            'nomenclatureActivitePrincipaleEtablissement',
                            'trancheEffectifsEtablissement',
                            'etatAdministratifEtablissement'
                        ]
                        
                    elif 'RNA' in name.upper():
                        critical_exact = [
                            'id',
                            'id_ex',
                            'siret',
                            'titre',
                            'titre_court',
                            'objet',
                            'adrs_numvoie',
                            'adrs_typevoie',
                            'adrs_libvoie',
                            'adrs_codepostal',
                            'adrs_libcommune'
                        ]
                    else:
                        critical_exact = []
                    
                    # Afficher seulement celles qui existent vraiment
                    found_count = 0
                    missing = []
                    for crit in critical_exact:
                        if crit in cols:
                            print(f"  ✅ {crit}")
                            found_count += 1
                        else:
                            missing.append(crit)
                    
                    if missing:
                        print(f"\n⚠️  Colonnes manquantes (vérifier les noms) :")
                        for m in missing:
                            print(f"  ❌ {m}")
                    
                    print(f"\n📊 {found_count}/{len(critical_exact)} colonnes critiques trouvées")
    
    except Exception as e:
        print(f"❌ Erreur : {e}")

def explore_gzip_with_delimiter(name, gz_path):
    """Explore un GZIP en détectant le séparateur"""
    print(f"\n{'='*60}")
    print(f"📂 EXPLORATION : {name}")
    print(f"{'='*60}")
    
    try:
        with gzip.open(gz_path, 'rt', encoding='utf-8') as f:
            header = f.readline().strip()
            
            if ';' in header and header.count(';') > header.count(','):
                delimiter = ';'
                print(f"⚠️  Séparateur : POINT-VIRGULE (;)")
            else:
                delimiter = ','
                print(f"✅ Séparateur : VIRGULE (,)")
            
            cols = [c.strip('\ufeff') for c in header.split(delimiter)]
            print(f"\n📊 {len(cols)} colonnes détectées\n")
            
            print(f"📋 TOUTES LES COLONNES BAN :")
            for i, c in enumerate(cols, 1):
                print(f"  {i:2d}. {c}")
            
            # ✅ LISTE EXPLICITE
            print(f"\n🔑 COLONNES CRITIQUES RECOMMANDÉES :")
            critical_exact = [
                'numero',
                'rep',
                'nom_voie',
                'code_postal',
                'code_insee',
                'nom_commune',
                'lat',
                'lon'
            ]
            
            found_count = 0
            missing = []
            for crit in critical_exact:
                if crit in cols:
                    print(f"  ✅ {crit}")
                    found_count += 1
                else:
                    missing.append(crit)
            
            if missing:
                print(f"\n⚠️  Colonnes manquantes :")
                for m in missing:
                    print(f"  ❌ {m}")
            
            print(f"\n📊 {found_count}/{len(critical_exact)} colonnes critiques trouvées")
                
    except Exception as e:
        print(f"❌ Erreur : {e}")

# 🚀 EXPLORATION COMPLÈTE
explore_zip_with_delimiter("SIRENE", "data/raw/StockEtablissement_utf8.zip")
explore_zip_with_delimiter("RNA", "data/raw/rna_waldec.zip")
explore_gzip_with_delimiter("BAN", "data/raw/adresses-france.csv.gz")

print("\n" + "="*60)
print("✅ EXPLORATION TERMINÉE")
print("="*60)
print("\n💡 Les colonnes listées ci-dessus sont à utiliser dans 01_extract.py")


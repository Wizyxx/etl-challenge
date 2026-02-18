#!/usr/bin/env python3
"""
Analyse : pourquoi seulement 9748 codes postaux ?
Hypothèse : la validation clean_postal_series() rejette des CP valides
"""
import duckdb
con = duckdb.connect('data/processed/unified_data.duckdb', read_only=True)

print("=" * 60)
print("ANALYSE : Distribution des codes postaux")
print("=" * 60)

# Top 20 CP par nombre d'établissements
top_cp = con.execute("""
    SELECT postal_code, COUNT(*) as n
    FROM unified_records
    WHERE postal_code IS NOT NULL
    GROUP BY postal_code
    ORDER BY n DESC
    LIMIT 20
""").fetchall()
print("\nTop 20 codes postaux :")
for cp, n in top_cp:
    print(f"  {cp} : {n:>8,} établissements")

# Vérifier s'il existe des CP rejetés dans sirene_raw
print("\n" + "=" * 60)
print("CP dans sirene_raw qui ont été rejetés")
print("=" * 60)

# Charger un échantillon de codePostalEtablissement depuis sirene
sample_raw = con.execute("""
    SELECT DISTINCT codePostalEtablissement, COUNT(*) as n
    FROM sirene
    WHERE codePostalEtablissement IS NOT NULL
      AND LENGTH(TRIM(codePostalEtablissement)) > 0
    GROUP BY codePostalEtablissement
    ORDER BY n DESC
    LIMIT 30
""").fetchall()
print("\nTop 30 CP dans sirene (avant nettoyage) :")
for cp, n in sample_raw:
    clean_cp = con.execute("""
        SELECT postal_code FROM unified_records 
        WHERE postal_code = ? LIMIT 1
    """, [cp.zfill(5) if len(cp) < 5 else cp]).fetchone()
    status = "✓ OK" if clean_cp else "✗ REJETÉ"
    print(f"  {cp:10s} → {cp.zfill(5) if len(cp)<5 else cp:5s}  {status:10s}  ({n:>6,} établ.)")

con.close()
#!/usr/bin/env python3
"""
Diagnostic synthétique - résultats concis uniquement
"""
import duckdb
import pyarrow.parquet as pq
import pandas as pd
from pathlib import Path

PROCESSED = Path("data/processed")
DB_PATH   = PROCESSED / "unified_data.duckdb"
con = duckdb.connect(str(DB_PATH), read_only=True)

# ─── 1. TAUX DE NULL colonnes clés ────────────────────────────────────────────
print("=" * 60)
print("1. TAUX NULL dans sirene_clean (sur 500k lignes échantillon)")
print("=" * 60)
pf = pq.ParquetFile(PROCESSED / "sirene_clean.parquet")
df = next(pf.iter_batches(batch_size=500_000)).to_pandas()
total = len(df)
for col in ['name', 'enseigne', 'addr_street', 'postal_code', 'ban_key']:
    pct = 100 * df[col].isna().sum() / total
    print(f"  {col:20s} : {pct:5.1f}% NULL")

# 1 exemple name=NULL vs name renseigné
ex_null = df[df['name'].isna()][['siret','name','enseigne']].head(1).to_dict('records')
ex_ok   = df[df['name'].notna()][['siret','name','enseigne']].head(1).to_dict('records')
print(f"  ex name=NULL  : {ex_null}")
print(f"  ex name=OK    : {ex_ok}")

# ─── 2. CROIX ROUGE ────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("2. CROIX ROUGE (SIREN 775672272)")
print("=" * 60)
found = False
pf2 = pq.ParquetFile(PROCESSED / "sirene_raw.parquet")
for batch in pf2.iter_batches(batch_size=500_000,
        columns=['siret','siren','denominationUsuelleEtablissement','enseigne1Etablissement']):
    match = batch.to_pandas().query("siren == '775672272'")
    if len(match):
        print(f"  TROUVÉ dans sirene_raw : {len(match)} ligne(s)")
        print(f"  siret={match.iloc[0]['siret']}  denom='{match.iloc[0]['denominationUsuelleEtablissement']}'  enseigne='{match.iloc[0]['enseigne1Etablissement']}'")
        found = True
        break
if not found:
    print("  ABSENT de sirene_raw → pas dans le fichier source INSEE")

# ─── 3. DINUM - ban_key ────────────────────────────────────────────────────────
print()
print("=" * 60)
print("3. DINUM ban_key vs BAN")
print("=" * 60)
row = con.execute("""
    SELECT ban_key, addr_num, addr_type, addr_street, postal_code
    FROM unified_records WHERE siret = '13002526500013'
""").fetchone()
if row:
    bk, num, typ, street, cp = row
    print(f"  ban_key SIRENE  : '{bk}'")
    match = con.execute("SELECT ban_key FROM ban WHERE ban_key = ?", [bk]).fetchone()
    print(f"  Match exact BAN : {'OUI' if match else 'NON'}")
    # Chercher la vraie clé dans BAN pour ce CP + voie
    alts = con.execute("""
        SELECT ban_key FROM ban
        WHERE code_postal = ? AND nom_voie LIKE '%SEGUR%'
        LIMIT 3
    """, [cp]).fetchall()
    print(f"  Clés BAN proches (75007+SEGUR) : {[r[0] for r in alts]}")

# ─── 4. CODES POSTAUX ──────────────────────────────────────────────────────────
print()
print("=" * 60)
print("4. CODES POSTAUX")
print("=" * 60)
r = con.execute("""
    SELECT
        COUNT(*) AS total,
        COUNT(postal_code) AS avec_cp,
        COUNT(DISTINCT postal_code) AS distincts,
        SUM(CASE WHEN postal_code IS NULL THEN 1 ELSE 0 END) AS sans_cp
    FROM unified_records
""").fetchone()
print(f"  Total lignes      : {r[0]:,}")
print(f"  Avec postal_code  : {r[1]:,} ({100*r[1]/r[0]:.1f}%)")
print(f"  Sans postal_code  : {r[3]:,} ({100*r[3]/r[0]:.1f}%)")
print(f"  CP distincts      : {r[2]:,}")
print(f"  stats_by_postal   : {con.execute('SELECT COUNT(*) FROM stats_by_postal').fetchone()[0]:,}")
# Exemples de codes qui manquent dans stats
ex_missing = con.execute("""
    SELECT DISTINCT u.postal_code
    FROM unified_records u
    WHERE u.postal_code IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM stats_by_postal s WHERE s.postal_code = u.postal_code)
    LIMIT 5
""").fetchall()
print(f"  Exemples CP absents de stats : {[r[0] for r in ex_missing]}")

# ─── 5. NAME NULL dans unified ─────────────────────────────────────────────────
print()
print("=" * 60)
print("5. NAME NULL dans unified_records")
print("=" * 60)
r2 = con.execute("""
    SELECT
        COUNT(*) AS total,
        SUM(CASE WHEN name IS NULL THEN 1 ELSE 0 END) AS null_name,
        SUM(CASE WHEN enseigne IS NOT NULL THEN 1 ELSE 0 END) AS has_enseigne
    FROM unified_records
""").fetchone()
print(f"  name=NULL     : {r2[1]:,} / {r2[0]:,} ({100*r2[1]/r2[0]:.1f}%)")
print(f"  enseigne≠NULL : {r2[2]:,} ({100*r2[2]/r2[0]:.1f}%) → fallback possible")

con.close()
print()
print("=" * 60)
print("FIN DU DIAGNOSTIC")
print("=" * 60)
#!/usr/bin/env python3
"""
Vérifie le contenu exact des archives pour détecter les fichiers manqués.
A lancer AVANT de relancer l'extraction.
"""
import zipfile
import gzip
from pathlib import Path

RAW_DIR = Path("data/raw")

# ─── SIRENE ───────────────────────────────────────────────────────────────────
print("=" * 60)
print("SIRENE — contenu du ZIP")
print("=" * 60)
with zipfile.ZipFile(RAW_DIR / "StockEtablissement_utf8.zip") as z:
    all_files = z.namelist()
    print(f"Nombre total de fichiers dans l'archive : {len(all_files)}")
    for f in all_files:
        info = z.getinfo(f)
        print(f"  {f:60s}  {info.file_size/1e6:8.1f} Mo")

# ─── RNA ──────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("RNA — contenu du ZIP (résumé)")
print("=" * 60)
with zipfile.ZipFile(RAW_DIR / "rna_waldec.zip") as z:
    all_files = z.namelist()
    csv_files = [f for f in all_files if f.endswith('.csv')]
    total_size = sum(z.getinfo(f).file_size for f in csv_files)
    print(f"Nombre de fichiers CSV : {len(csv_files)}")
    print(f"Taille totale décompressée : {total_size/1e9:.2f} Go")
    # 5 premiers et 5 derniers
    for f in csv_files[:3]:
        info = z.getinfo(f)
        print(f"  {f:50s}  {info.file_size/1e6:.1f} Mo")
    print("  ...")
    for f in csv_files[-3:]:
        info = z.getinfo(f)
        print(f"  {f:50s}  {info.file_size/1e6:.1f} Mo")

# ─── BAN ──────────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("BAN — taille réelle du GZ")
print("=" * 60)
gz_path = RAW_DIR / "adresses-france.csv.gz"
print(f"Taille compressée   : {gz_path.stat().st_size/1e9:.2f} Go")
# Lire juste le header pour confirmer
with gzip.open(gz_path, 'rt') as f:
    header = f.readline().strip()
    ncols = len(header.split(';'))
print(f"Colonnes : {ncols}")
print(f"Header   : {header[:120]}...")

# ─── PARQUETS ─────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("PARQUETS — row counts réels")
print("=" * 60)
import pyarrow.parquet as pq
PROCESSED = Path("data/processed")
for name in ["sirene_raw", "rna_raw", "ban_raw",
             "sirene_clean", "rna_clean", "ban_clean"]:
    p = PROCESSED / f"{name}.parquet"
    if p.exists():
        pf = pq.ParquetFile(p)
        n  = pf.metadata.num_rows
        sz = p.stat().st_size / 1e9
        print(f"  {name:20s} : {n:>15,} lignes  /  {sz:.2f} Go")
    else:
        print(f"  {name:20s} : ABSENT")
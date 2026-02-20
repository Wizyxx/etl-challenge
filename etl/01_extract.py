#!/usr/bin/env python3
"""
ETL CHALLENGE - PHASE 1: EXTRACTION (v3)
Sources :
  - StockEtablissement_utf8.zip  → sirene_raw.parquet
  - StockUniteLegale_utf8.zip    → unite_legale_raw.parquet  (noms entreprises)
  - rna_waldec.zip               → rna_raw.parquet
  - adresses-france.csv.gz       → ban_raw.parquet
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import zipfile
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

RAW_DIR           = Path("data_raw")
PROCESSED         = Path("data_parquet")
PROCESSED.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE_SIRENE = 50_000
CHUNK_SIZE_BAN    = 50_000


def make_schema(cols, str_cols, bool_cols=None):
    """
    Construit un schéma PyArrow explicite pour éviter les conflits null/string
    entre chunks. Toutes les colonnes str_cols sont forcées en pa.string(),
    les bool_cols en pa.bool_().
    """
    fields = []
    for col in cols:
        if bool_cols and col in bool_cols:
            fields.append(pa.field(col, pa.bool_()))
        else:
            fields.append(pa.field(col, pa.string()))
    return pa.schema(fields)


class ParquetStreamWriter:
    """Écrit chunk par chunk dans un Parquet sans accumuler en RAM.
    Le schéma est fourni explicitement pour éviter les conflits null/string."""
    def __init__(self, path: Path, schema: pa.Schema):
        self.path    = path
        self.schema  = schema
        self._writer = None

    def write(self, df: pd.DataFrame):
        # Cast explicite : toutes les colonnes string sont forcées en str
        # avant la conversion PyArrow — évite l'inférence null sur chunks vides
        for field in self.schema:
            if field.type == pa.string() and field.name in df.columns:
                df[field.name] = df[field.name].fillna('').astype(str).replace('', None)
        table = pa.Table.from_pandas(df, schema=self.schema, preserve_index=False)
        if self._writer is None:
            self._writer = pq.ParquetWriter(str(self.path), self.schema,
                                            compression='snappy')
        self._writer.write_table(table)

    def close(self):
        if self._writer:
            self._writer.close()
            self._writer = None


# =============================================================================
# 1. SIRENE (établissements)
# =============================================================================
SIRENE_COLS = [
    'siret', 'siren', 'etablissementSiege',
    'denominationUsuelleEtablissement', 'enseigne1Etablissement',
    'numeroVoieEtablissement', 'indiceRepetitionEtablissement',
    'typeVoieEtablissement', 'libelleVoieEtablissement',
    'codePostalEtablissement', 'libelleCommuneEtablissement',
    'codeCommuneEtablissement', 'activitePrincipaleEtablissement',
    'nomenclatureActivitePrincipaleEtablissement',
    'trancheEffectifsEtablissement', 'etatAdministratifEtablissement',
    'caractereEmployeurEtablissement',
]
SIRENE_DTYPES = {col: 'str' for col in SIRENE_COLS if col != 'etablissementSiege'}
SIRENE_SCHEMA = make_schema(SIRENE_COLS, SIRENE_DTYPES, bool_cols=['etablissementSiege'])

def extract_sirene():
    out = PROCESSED / "sirene_raw.parquet"
    if out.exists():
        logger.info("SIRENE déjà extrait, skip.")
        return
    logger.info("🏢 SIRENE — extraction streaming...")
    writer = ParquetStreamWriter(out, SIRENE_SCHEMA)
    total  = 0
    with zipfile.ZipFile(RAW_DIR / "StockEtablissement_utf8.zip") as z:
        csv_file = [f for f in z.namelist() if f.endswith('.csv')][0]
        logger.info(f"   Fichier : {csv_file}")
        with z.open(csv_file) as raw:
            for i, chunk in enumerate(pd.read_csv(
                raw, sep=',', encoding='utf-8',
                usecols=SIRENE_COLS, dtype=SIRENE_DTYPES,
                chunksize=CHUNK_SIZE_SIRENE,
                low_memory=False, on_bad_lines='warn',
            )):
                writer.write(chunk)
                total += len(chunk)
                if (i + 1) % 20 == 0:
                    logger.info(f"   -> {total:>10,} lignes...")
    writer.close()
    logger.info(f"OK SIRENE : {total:,} lignes -> {out}")


# =============================================================================
# 2. UNITE LEGALE
# =============================================================================
UL_COLS = [
    'siren',
    'denominationUniteLegale',
    'nomUniteLegale',
    'prenom1UniteLegale',
    'categorieJuridiqueUniteLegale',
    'categorieEntreprise',
]
UL_DTYPES  = {col: 'str' for col in UL_COLS}
UL_SCHEMA  = make_schema(UL_COLS, UL_DTYPES)

def extract_unite_legale():
    out     = PROCESSED / "unite_legale_raw.parquet"
    ul_path = RAW_DIR / "StockUniteLegale_utf8.zip"

    if out.exists():
        logger.info("UniteLegale déjà extrait, skip.")
        return
    if not ul_path.exists():
        logger.warning("⚠️  StockUniteLegale_utf8.zip absent de data_raw/")
        return

    logger.info("🏛️  UniteLegale — extraction streaming...")
    writer = ParquetStreamWriter(out, UL_SCHEMA)
    total  = 0
    with zipfile.ZipFile(ul_path) as z:
        csv_file = [f for f in z.namelist() if f.endswith('.csv')][0]
        logger.info(f"   Fichier : {csv_file}")
        with z.open(csv_file) as raw:
            for i, chunk in enumerate(pd.read_csv(
                raw, sep=',', encoding='utf-8',
                usecols=lambda c: c in UL_COLS,
                dtype=UL_DTYPES,
                chunksize=CHUNK_SIZE_SIRENE,
                low_memory=False, on_bad_lines='warn',
            )):
                writer.write(chunk)
                total += len(chunk)
                if (i + 1) % 20 == 0:
                    logger.info(f"   -> {total:>10,} lignes...")
    writer.close()
    logger.info(f"OK UniteLegale : {total:,} lignes -> {out}")


# =============================================================================
# 3. RNA
# =============================================================================
RNA_COLS = [
    'id', 'id_ex', 'siret', 'titre', 'titre_court', 'objet',
    'adrs_numvoie', 'adrs_repetition', 'adrs_typevoie', 'adrs_libvoie',
    'adrs_codepostal', 'adrs_libcommune',
    'date_publi', 'nature', 'groupement',
]
RNA_DTYPES = {col: 'str' for col in RNA_COLS}
RNA_SCHEMA = make_schema(RNA_COLS, RNA_DTYPES)

def extract_rna():
    out = PROCESSED / "rna_raw.parquet"
    if out.exists():
        logger.info("RNA déjà extrait, skip.")
        return
    logger.info("🤝 RNA — extraction (104 fichiers)...")
    writer = ParquetStreamWriter(out, RNA_SCHEMA)
    total  = 0
    with zipfile.ZipFile(RAW_DIR / "rna_waldec.zip") as z:
        csv_files = sorted(f for f in z.namelist() if f.endswith('.csv'))
        logger.info(f"   {len(csv_files)} fichiers CSV")
        for idx, fname in enumerate(csv_files, 1):
            try:
                with z.open(fname) as raw:
                    try:
                        df = pd.read_csv(raw, sep=';', encoding='utf-8',
                                         usecols=lambda c: c in RNA_COLS,
                                         dtype=RNA_DTYPES, low_memory=False,
                                         on_bad_lines='skip')
                    except UnicodeDecodeError:
                        with z.open(fname) as raw2:
                            df = pd.read_csv(raw2, sep=';', encoding='latin-1',
                                             usecols=lambda c: c in RNA_COLS,
                                             dtype=RNA_DTYPES, low_memory=False,
                                             on_bad_lines='skip')
                    # Ajouter les colonnes manquantes avec None
                    for col in RNA_COLS:
                        if col not in df.columns:
                            df[col] = None
                    df = df[RNA_COLS]  # ordre fixe
                    df['siret'] = df['siret'].str.strip().replace(
                        {'': None, 'nan': None, '0000000000000': None})
                    writer.write(df)
                    total += len(df)
            except Exception as e:
                logger.warning(f"   Skip {fname}: {e}")
            if idx % 25 == 0:
                logger.info(f"   -> {idx}/{len(csv_files)} fichiers — {total:,} lignes")
    writer.close()
    logger.info(f"OK RNA : {total:,} associations -> {out}")


# =============================================================================
# 4. BAN
# =============================================================================
BAN_COLS   = ['numero', 'rep', 'nom_voie', 'code_postal', 'code_insee',
              'nom_commune', 'lat', 'lon']
BAN_DTYPES = {'numero': 'str', 'rep': 'str', 'nom_voie': 'str',
              'code_postal': 'str', 'code_insee': 'str', 'nom_commune': 'str',
              'lat': 'float32', 'lon': 'float32'}
BAN_SCHEMA = pa.schema([
    pa.field('numero',      pa.string()),
    pa.field('rep',         pa.string()),
    pa.field('nom_voie',    pa.string()),
    pa.field('code_postal', pa.string()),
    pa.field('code_insee',  pa.string()),
    pa.field('nom_commune', pa.string()),
    pa.field('lat',         pa.float32()),
    pa.field('lon',         pa.float32()),
])

def extract_ban():
    out = PROCESSED / "ban_raw.parquet"
    if out.exists():
        logger.info("BAN déjà extrait, skip.")
        return
    logger.info("🗺️  BAN — extraction streaming (~50M lignes)...")
    writer  = ParquetStreamWriter(out, BAN_SCHEMA)
    total   = 0
    skipped = 0
    for i, chunk in enumerate(pd.read_csv(
        RAW_DIR / "adresses-france.csv.gz",
        sep=';', compression='gzip',
        usecols=BAN_COLS, dtype=BAN_DTYPES,
        chunksize=CHUNK_SIZE_BAN,
        low_memory=False, on_bad_lines='warn',
    )):
        before   = len(chunk)
        chunk    = chunk.dropna(subset=['lat', 'lon'])
        skipped += before - len(chunk)
        writer.write(chunk)
        total += len(chunk)
        if (i + 1) % 50 == 0:
            logger.info(f"   -> {total:>12,} adresses valides...")
    writer.close()
    logger.info(f"OK BAN : {total:,} adresses -> {out} ({skipped:,} sans GPS ignorées)")


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("PHASE 1 — EXTRACTION (v3)")
    logger.info("=" * 60)
    extract_sirene()
    extract_unite_legale()
    extract_rna()
    extract_ban()
    logger.info("=" * 60)
    logger.info("EXTRACTION TERMINEE")
    logger.info("=" * 60)
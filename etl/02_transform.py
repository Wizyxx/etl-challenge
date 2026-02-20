#!/usr/bin/env python3
"""
ETL CHALLENGE - PHASE 2: TRANSFORMATION (v3)
Lit depuis data_parquet/*_raw.parquet
Aucun accès aux ZIP — c'est le rôle de 01_extract.py
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import re
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

PROCESSED  = Path("data_parquet")
BATCH_SIZE = 500_000

TYPE_VOIE_MAP = {
    'ALL': 'ALLEE', 'AV': 'AVENUE', 'AVE': 'AVENUE',
    'BD': 'BOULEVARD', 'BLVD': 'BOULEVARD',
    'CAR': 'CARREFOUR', 'CHE': 'CHEMIN', 'CHS': 'CHAUSSEE',
    'CITE': 'CITE', 'COR': 'CORNICHE', 'CRS': 'COURS',
    'DOM': 'DOMAINE', 'DSC': 'DESCENTE', 'ECA': 'ECART',
    'ESP': 'ESPLANADE', 'FG': 'FAUBOURG', 'GR': 'GRANDE RUE',
    'HAM': 'HAMEAU', 'HLE': 'HALLE', 'IMP': 'IMPASSE',
    'LD': 'LIEU DIT', 'LOT': 'LOTISSEMENT', 'MAR': 'MARCHE',
    'MTE': 'MONTEE', 'PAS': 'PASSAGE', 'PL': 'PLACE',
    'PLN': 'PLAINE', 'PLT': 'PLATEAU', 'PRO': 'PROMENADE',
    'PRV': 'PARVIS', 'QUA': 'QUARTIER', 'QUAI': 'QUAI',
    'RES': 'RESIDENCE', 'RLE': 'RUELLE', 'ROC': 'ROCADE',
    'RPT': 'ROND POINT', 'RTE': 'ROUTE', 'RUE': 'RUE',
    'SEN': 'SENTIER', 'SQ': 'SQUARE', 'TPL': 'TERRE PLEIN',
    'TRA': 'TRAVERSE', 'VLA': 'VILLA', 'VLGE': 'VILLAGE',
    'VOI': 'VOIE', 'ZA': 'ZONE ARTISANALE', 'ZAC': 'ZAC',
    'ZAD': 'ZAD', 'ZI': 'ZONE INDUSTRIELLE', 'ZUP': 'ZUP',
}

_RE_SPACES = re.compile(r'\s+')

def clean_str_series(s: pd.Series) -> pd.Series:
    return (s.fillna('').astype(str).str.strip().str.upper()
             .str.replace(_RE_SPACES, ' ', regex=True).replace('', None))

def clean_postal_series(s: pd.Series) -> pd.Series:
    c = s.fillna('').astype(str).str.strip()
    c = c.where(c.str.len() >= 5, c.str.zfill(5))
    valid = c.str.match(r'^\d{5}$')
    return c.where(valid, other=None)

def clean_siret_series(s: pd.Series) -> pd.Series:
    c = s.fillna('').astype(str).str.strip().str.replace(r'\D', '', regex=True)
    return c.where(c.str.len() == 14, other=None)

def normalize_type_voie(s: pd.Series) -> pd.Series:
    return s.map(lambda x: TYPE_VOIE_MAP.get(
        str(x).strip().upper(), str(x).strip().upper()) if pd.notna(x) else None)

def build_ban_key(num, rep, type_v, lib_v, cp):
    n  = num.fillna('').astype(str).str.strip()
    r  = rep.fillna('').astype(str).str.strip().str.upper()
    tv = normalize_type_voie(type_v).fillna('')
    lv = lib_v.fillna('')
    voie = (tv + ' ' + lv).str.strip()
    return cp.fillna('') + '_' + (n + r) + '_' + voie


# =============================================================================
# CHARGER LES NOMS DEPUIS unite_legale_raw.parquet
# =============================================================================

def transform_sirene():
    """
    Transformation SIRENE.
    NOTE : le champ 'name' n est PAS résolu ici.
    La jointure avec UniteLegale se fait dans 03_load.py (DuckDB SQL, sans coût RAM).
    On conserve seulement 'siren' pour que DuckDB puisse faire la jointure.
    """
    dst = PROCESSED / "sirene_clean.parquet"
    if dst.exists():
        logger.info("SIRENE transform déjà fait, skip.")
        return

    logger.info("Transformation SIRENE (depuis sirene_raw.parquet)...")
    pf     = pq.ParquetFile(PROCESSED / "sirene_raw.parquet")
    writer = None
    total  = 0
    valid  = 0

    for batch in pf.iter_batches(batch_size=BATCH_SIZE):
        df = batch.to_pandas()
        total += len(df)

        df['siret'] = clean_siret_series(df['siret'])
        df = df[df['siret'].notna()].copy()
        valid += len(df)

        # Nom local : denominationUsuelle ou enseigne (si dispo dans l établissement)
        # Le vrai nom sera ajouté par jointure UniteLegale dans 03_load.py
        df['name_etab']  = clean_str_series(df['denominationUsuelleEtablissement'])
        df['enseigne']   = clean_str_series(df['enseigne1Etablissement'])

        df['addr_num']    = df['numeroVoieEtablissement'].fillna('').astype(str).str.strip()
        df['addr_rep']    = df['indiceRepetitionEtablissement'].fillna('').astype(str).str.strip().str.upper()
        df['addr_type']   = normalize_type_voie(df['typeVoieEtablissement'])
        df['addr_street'] = clean_str_series(df['libelleVoieEtablissement'])
        df['postal_code'] = clean_postal_series(df['codePostalEtablissement'])
        df['city']        = clean_str_series(df['libelleCommuneEtablissement'])
        df['commune_id']  = df['codeCommuneEtablissement'].fillna('').str.strip()
        df['naf']         = clean_str_series(df['activitePrincipaleEtablissement'])
        df['status']      = df['etatAdministratifEtablissement'].map(
                                {'A': 'open', 'F': 'closed'}).fillna('unknown')

        df['ban_key'] = build_ban_key(
            df['addr_num'], df['addr_rep'],
            df['addr_type'], df['addr_street'], df['postal_code'])

        keep = ['siret', 'siren', 'name_etab', 'enseigne',
                'addr_num', 'addr_rep', 'addr_type', 'addr_street',
                'postal_code', 'city', 'commune_id',
                'naf', 'status', 'ban_key',
                'etablissementSiege', 'caractereEmployeurEtablissement']
        df = df[[c for c in keep if c in df.columns]]

        table = pa.Table.from_pandas(df, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(str(dst), table.schema, compression='snappy')
        writer.write_table(table)
        logger.info(f"   -> {valid:>10,} valides / {total:,} lus...")

    if writer:
        writer.close()
    logger.info(f"OK SIRENE : {valid:,} -> {dst}")


def transform_rna():
    dst = PROCESSED / "rna_clean.parquet"
    if dst.exists():
        logger.info("RNA transform déjà fait, skip.")
        return

    logger.info("Transformation RNA (depuis rna_raw.parquet)...")
    df = pd.read_parquet(PROCESSED / "rna_raw.parquet")
    logger.info(f"   {len(df):,} lignes")

    df['id_rna']          = df['id'].astype(str).str.strip()
    df['siret']           = clean_siret_series(df['siret'])
    df['titre_clean']     = clean_str_series(df['titre'])
    df['adrs_numvoie']    = df['adrs_numvoie'].fillna('').astype(str).str.strip()
    df['adrs_repetition'] = df.get('adrs_repetition',
        pd.Series('', index=df.index)).fillna('').astype(str).str.upper()
    df['adrs_typevoie']   = normalize_type_voie(df['adrs_typevoie'])
    df['adrs_libvoie']    = clean_str_series(df['adrs_libvoie'])
    df['adrs_codepostal'] = clean_postal_series(df['adrs_codepostal'])
    df['date_publi']      = pd.to_datetime(df['date_publi'], errors='coerce')

    df['ban_key'] = build_ban_key(
        df['adrs_numvoie'], df['adrs_repetition'],
        df['adrs_typevoie'], df['adrs_libvoie'], df['adrs_codepostal'])

    keep = ['id_rna', 'siret', 'titre_clean', 'date_publi',
            'adrs_numvoie', 'adrs_typevoie', 'adrs_libvoie',
            'adrs_codepostal', 'adrs_libcommune', 'nature', 'ban_key']
    df = df[[c for c in keep if c in df.columns]]
    df.to_parquet(dst, index=False, compression='snappy')
    logger.info(f"OK RNA : {len(df):,} -> {dst} | avec SIRET: {df['siret'].notna().sum():,}")


# =============================================================================
# 3. TRANSFORM BAN (lit ban_raw.parquet)
# =============================================================================
def transform_ban():
    dst = PROCESSED / "ban_clean.parquet"
    if dst.exists():
        logger.info("BAN transform déjà fait, skip.")
        return

    logger.info("Transformation BAN (depuis ban_raw.parquet)...")
    pf     = pq.ParquetFile(PROCESSED / "ban_raw.parquet")
    writer = None
    total  = 0

    for batch in pf.iter_batches(batch_size=BATCH_SIZE):
        df = batch.to_pandas()
        df['numero']      = df['numero'].fillna('').astype(str).str.strip()
        df['rep']         = df['rep'].fillna('').astype(str).str.strip().str.upper()
        df['nom_voie']    = clean_str_series(df['nom_voie'])
        df['code_postal'] = clean_postal_series(df['code_postal'])
        df['nom_commune'] = clean_str_series(df['nom_commune'])
        df = df[df['lat'].between(-90, 90) & df['lon'].between(-180, 180)].copy()

        # Clé BAN : même format que SIRENE (cp_num_TYPE VOIE)
        n  = df['numero'].fillna('')
        r  = df['rep'].fillna('')
        voi = df['nom_voie'].fillna('')
        cp  = df['code_postal'].fillna('')
        df['ban_key'] = cp + '_' + (n + r) + '_' + voi

        total += len(df)
        table = pa.Table.from_pandas(df, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(str(dst), table.schema, compression='snappy')
        writer.write_table(table)
        logger.info(f"   -> {total:>12,} adresses...")

    if writer:
        writer.close()
    logger.info(f"OK BAN : {total:,} -> {dst}")


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("PHASE 2 — TRANSFORMATION (v3)")
    logger.info("=" * 60)
    transform_sirene()
    transform_rna()
    transform_ban()
    logger.info("=" * 60)
    logger.info("TRANSFORMATION TERMINEE")
    logger.info("=" * 60)
#!/usr/bin/env python3
"""
ETL CHALLENGE — Téléchargement des sources brutes
Fonctionnel pour les 3+1 URLs sources :
  1. StockEtablissement_utf8.zip   (SIRENE établissements)
  2. StockUniteLegale_utf8.zip     (SIRENE noms)
  3. rna_waldec.zip                (RNA — associations)
  4. adresses-france.csv.gz        (BAN — adresses)

Edge cases gérés :
  - Skip si fichier déjà présent ET taille cohérente
  - Vérification Content-Length vs taille locale post-download
  - Retry automatique (3 tentatives)
  - Timeout configurable
  - Stockage local uniquement (aucun appel API externe)
"""

import os
import sys
import time
import logging
import hashlib
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

RAW_DIR = Path("data_raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# SOURCES — URLs officielles (data.gouv.fr, interieur.gouv.fr, adresse.data.gouv.fr)
# Aucun appel API externe : téléchargement direct de fichiers statiques.
# ─────────────────────────────────────────────────────────────────────────────

SOURCES = [
    {
        "name": "SIRENE Établissements",
        "url":  "https://object.files.data.gouv.fr/data-pipeline-open/siren/stock/StockEtablissement_utf8.zip",
        "dest": RAW_DIR / "StockEtablissement_utf8.zip",
        "min_size_mb": 500,     # ~4 Go attendu, minimum 500 Mo pour être valide
    },
    {
        "name": "SIRENE Unités Légales",
        "url":  "https://object.files.data.gouv.fr/data-pipeline-open/siren/stock/StockUniteLegale_utf8.zip",
        "dest": RAW_DIR / "StockUniteLegale_utf8.zip",
        "min_size_mb": 200,     # ~1.5 Go attendu
    },
    {
        "name": "RNA (Associations)",
        "url":  "https://media.interieur.gouv.fr/rna/rna_waldec_20250901.zip",
        "dest": RAW_DIR / "rna_waldec.zip",
        "min_size_mb": 50,      # ~500 Mo attendu
    },
    {
        "name": "BAN (Adresses)",
        "url":  "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/adresses-france.csv.gz",
        "dest": RAW_DIR / "adresses-france.csv.gz",
        "min_size_mb": 500,     # ~4 Go attendu
    },
]

CHUNK_SIZE    = 1024 * 1024     # 1 Mo par chunk
MAX_RETRIES   = 3
TIMEOUT_S     = 30              # timeout connexion (pas lecture)
MANIFEST_PATH = RAW_DIR / ".checksums.md5"


# ─────────────────────────────────────────────────────────────────────────────
# FONCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def load_manifest() -> dict[str, str]:
    """Charge le fichier manifest MD5 (nom_fichier -> hash md5)."""
    manifest = {}
    if MANIFEST_PATH.exists():
        for line in MANIFEST_PATH.read_text().strip().splitlines():
            parts = line.split("  ", 1)
            if len(parts) == 2:
                manifest[parts[1].strip()] = parts[0].strip()
    return manifest


def save_manifest(manifest: dict[str, str]):
    """Sauvegarde le manifest MD5 au format standard (md5sum-compatible)."""
    lines = [f"{h}  {name}" for name, h in sorted(manifest.items())]
    MANIFEST_PATH.write_text("\n".join(lines) + "\n")


def compute_md5(path: Path) -> str:
    """Calcule le hash MD5 d'un fichier (lecture par chunks pour fichiers > RAM)."""
    h = hashlib.md5()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def get_remote_size(url: str) -> int | None:
    """Récupère le Content-Length distant via HEAD (sans télécharger)."""
    try:
        req = Request(url, method='HEAD')
        with urlopen(req, timeout=TIMEOUT_S) as resp:
            cl = resp.headers.get('Content-Length')
            return int(cl) if cl else None
    except Exception:
        return None


def verify_file(path: Path, expected_size: int | None, min_size_mb: int) -> bool:
    """
    Vérifie qu'un fichier local est complet :
      1. Existe
      2. Taille >= seuil minimum (protège contre les fichiers tronqués)
      3. Si Content-Length connu : taille locale == taille distante
    """
    if not path.exists():
        return False

    local_size = path.stat().st_size
    min_bytes  = min_size_mb * 1024 * 1024

    if local_size < min_bytes:
        logger.warning(f"   {path.name} trop petit ({local_size / 1e6:.0f} Mo < {min_size_mb} Mo minimum)")
        return False

    if expected_size is not None and local_size != expected_size:
        logger.warning(f"   Taille {path.name} : {local_size:,} octets (attendu {expected_size:,})")
        return False

    return True


def download_file(url: str, dest: Path) -> int:
    """
    Télécharge un fichier par chunks avec barre de progression.
    Retourne la taille téléchargée.
    """
    req = Request(url, headers={"User-Agent": "ETL-Challenge/1.0"})
    with urlopen(req, timeout=TIMEOUT_S) as resp:
        total = resp.headers.get('Content-Length')
        total = int(total) if total else None

        downloaded = 0
        tmp_path = dest.with_suffix(dest.suffix + '.tmp')

        with open(tmp_path, 'wb') as f:
            while True:
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                if total:
                    pct = downloaded / total * 100
                    print(f"\r   ↓ {downloaded / 1e6:.0f} / {total / 1e6:.0f} Mo ({pct:.1f}%)", end='', flush=True)
                else:
                    print(f"\r   ↓ {downloaded / 1e6:.0f} Mo", end='', flush=True)

        print()  # newline après la barre de progression

        # Vérification post-téléchargement : taille cohérente
        if total is not None and downloaded != total:
            tmp_path.unlink(missing_ok=True)
            raise IOError(f"Téléchargement incomplet : {downloaded:,} / {total:,} octets")

        # Renommage atomique (tmp → final) — évite les fichiers corrompus
        tmp_path.rename(dest)
        return downloaded


def download_source(source: dict, manifest: dict[str, str]) -> bool:
    """Télécharge une source avec retry + vérification MD5. Retourne True si succès."""
    name = source["name"]
    url  = source["url"]
    dest = source["dest"]
    min_mb = source["min_size_mb"]
    fname  = dest.name

    logger.info(f"{name}")

    # 1. Vérifier si déjà téléchargé et complet (taille + MD5)
    remote_size = get_remote_size(url)
    if verify_file(dest, remote_size, min_mb):
        # Vérification MD5 si le hash est connu dans le manifest
        if fname in manifest:
            logger.info(f"   Vérification MD5 de {fname}...")
            current_md5 = compute_md5(dest)
            if current_md5 == manifest[fname]:
                size_mb = dest.stat().st_size / 1e6
                logger.info(f"   Déjà présent, taille + MD5 OK ({size_mb:.0f} Mo) — skip")
                return True
            else:
                logger.warning(f"   MD5 différent (fichier modifié ou corrompu), re-téléchargement")
                dest.unlink(missing_ok=True)
        else:
            # Pas de hash connu : calculer et stocker pour les prochaines fois
            current_md5 = compute_md5(dest)
            manifest[fname] = current_md5
            save_manifest(manifest)
            size_mb = dest.stat().st_size / 1e6
            logger.info(f"   Déjà présent, taille OK ({size_mb:.0f} Mo), MD5 enregistré — skip")
            return True

    # 2. Télécharger avec retry
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"   Téléchargement (tentative {attempt}/{MAX_RETRIES})...")
            t0 = time.time()
            size = download_file(url, dest)
            elapsed = time.time() - t0
            speed = size / elapsed / 1e6 if elapsed > 0 else 0
            logger.info(f"   {size / 1e6:.0f} Mo en {elapsed:.0f}s ({speed:.1f} Mo/s)")

            # 3. Vérification post-download (taille)
            if not verify_file(dest, remote_size, min_mb):
                logger.error(f"   Vérification taille échouée après téléchargement")
                dest.unlink(missing_ok=True)
                continue

            # 4. Calcul et stockage du MD5
            logger.info(f"   Calcul MD5 de {fname}...")
            new_md5 = compute_md5(dest)
            manifest[fname] = new_md5
            save_manifest(manifest)
            logger.info(f"   MD5 : {new_md5}")
            return True

        except (URLError, HTTPError, IOError, OSError) as e:
            logger.error(f"   Erreur tentative {attempt} : {e}")
            dest.with_suffix(dest.suffix + '.tmp').unlink(missing_ok=True)
            if attempt < MAX_RETRIES:
                wait = 5 * attempt
                logger.info(f"   Attente {wait}s avant retry...")
                time.sleep(wait)

    logger.error(f"   ÉCHEC DÉFINITIF : {name}")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    logger.info("=" * 60)
    logger.info("TÉLÉCHARGEMENT DES SOURCES BRUTES")
    logger.info("Stockage local : %s", RAW_DIR.resolve())
    logger.info("=" * 60)

    manifest = load_manifest()
    results  = []
    for source in SOURCES:
        ok = download_source(source, manifest)
        results.append((source["name"], ok))

    # Bilan
    logger.info("")
    logger.info("=" * 60)
    ok_count   = sum(1 for _, ok in results if ok)
    fail_count = len(results) - ok_count

    for name, ok in results:
        status = "✅" if ok else "❌"
        logger.info(f"   {status} {name}")

    logger.info("")
    if fail_count == 0:
        logger.info(f"SUCCÈS : {ok_count}/{len(results)} sources téléchargées et vérifiées")
    else:
        logger.error(f"ATTENTION : {fail_count} source(s) en erreur")

    logger.info("=" * 60)
    return fail_count == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

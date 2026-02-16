#!/bin/bash

# Création du dossier de stockage
mkdir -p data/raw

echo "--- Début du téléchargement ---"

# 1. SIRENE (Ton lien direct qui fonctionne)
wget -O data/raw/StockEtablissement_utf8.zip \
  "https://object.files.data.gouv.fr/data-pipeline-open/siren/stock/StockEtablissement_utf8.zip"
# 2. RNA (Associations) ~100Mo
# 2. RNA (Associations - Lien direct Ministère)
wget -O data/raw/rna_waldec.zip "https://media.interieur.gouv.fr/rna/rna_waldec_20250901.zip"
# 3. BAN (Adresses) ~800Mo compressé / 9Go+ extrait
#wget -O data/raw/adresses-france.csv.gz "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/adresses-france.csv.gz"

echo "--- Téléchargement terminé avec succès ! ---"


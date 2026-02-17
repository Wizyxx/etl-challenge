#!/bin/bash

# Création du dossier de stockage
mkdir -p data/raw

echo "--- Vérification et Téléchargement des sources ---"

# Fonction pour télécharger uniquement si absent
download_if_missing() {
    local url=$1
    local dest=$2
    if [ -f "$dest" ]; then
        echo "✅ Déjà présent : $dest (skip)"
    else
        echo "🚀 Téléchargement de $(basename "$dest")..."
        wget -O "$dest" "$url"
    fi
}

# 1. SIRENE - Établissements
download_if_missing "https://object.files.data.gouv.fr/data-pipeline-open/siren/stock/StockEtablissement_utf8.zip" \
    "data/raw/StockEtablissement_utf8.zip"

# 2. SIRENE - Unités Légales
download_if_missing "https://object.files.data.gouv.fr/data-pipeline-open/siren/stock/StockUniteLegale_utf8.zip" \
    "data/raw/StockUniteLegale_utf8.zip"

# 3. RNA (Associations)
download_if_missing "https://media.interieur.gouv.fr/rna/rna_waldec_20250901.zip" \
    "data/raw/rna_waldec.zip"

# 4. BAN (Adresses)
download_if_missing "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/adresses-france.csv.gz" \
    "data/raw/adresses-france.csv.gz"

echo "--- Opération terminée ! ---"
#!/bin/bash
# ============================================================
# ETL CHALLENGE — Pipeline complet + lancement API
# ============================================================
set -e

echo "Activation de l'environnement virtuel..."
source venv/bin/activate

echo "Installation des dépendances…"
pip install -r requirements.txt

echo ""
echo "PHASE 1 — EXTRACTION"
python etl/01_extract.py

echo ""
echo "PHASE 2 — TRANSFORMATION"
python etl/02_transform.py

echo ""
echo "PHASE 3 — CHARGEMENT & JOINTURES"
python etl/03_load.py

echo ""
echo "PHASE 4 — VALIDATION"
python etl/04_validate.py

echo ""
echo "LANCEMENT DE L'API (port 8000)"
echo "   Endpoints disponibles :"
echo "   • GET /api/v1/ping"
echo "   • GET /api/v1/siret/{siret}"
echo "   • GET /api/v1/search?q=...&dept=..."
echo "   • GET /api/v1/stats/{code_postal}"
echo ""
cd etl && uvicorn api:app --host 0.0.0.0 --port 8000 --workers 4s
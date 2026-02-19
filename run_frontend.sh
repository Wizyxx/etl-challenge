#!/bin/bash
# ============================================================
# LANCEUR FRONTEND (Serveur Web)
# ============================================================
set -e

# Active l'environnement virtuel s'il existe
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
fi

echo ""
echo "LANCEMENT FRONTEND"
echo "Accès Site : http://localhost:5500"
echo ""
echo "Appuyez sur Ctrl+C pour arrêter."
echo ""

python3 -m http.server 5500
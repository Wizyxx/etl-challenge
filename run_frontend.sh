#!/bin/bash
# ============================================================
# LANCEUR FRONTEND (Serveur Web)
# 5 Days Challenge — Référentiel Unifié SIRENE × RNA × BAN
# ============================================================
set -e

# ─── Se placer dans le répertoire du script (peu importe d'où on le lance) ───
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "════════════════════════════════════════════"
echo "  FRONTEND — Référentiel Unifié"
echo "════════════════════════════════════════════"
echo "  Répertoire : $SCRIPT_DIR"
echo "  Accès site : http://localhost:5500"
echo ""
echo "  Ctrl+C pour arrêter."
echo "════════════════════════════════════════════"
echo ""

# ─── Vérification que index.html est bien présent ─────────────────────────
if [ ! -f "index.html" ]; then
    echo "ERREUR : index.html introuvable dans $SCRIPT_DIR"
    echo "Vérifiez que run_frontend.sh est dans le même dossier que index.html."
    exit 1
fi

# ─── Lancement du serveur web ─────────────────────────────────────────────
python3 -m http.server 5500
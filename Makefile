# ─────────────────────────────────────────────────────────────────────────────
# ETL CHALLENGE — Makefile
# Usage : make <cible>
# ─────────────────────────────────────────────────────────────────────────────

PYTHON   := python3
VENV     := venv
PIP      := $(VENV)/bin/pip
PYRUN    := $(VENV)/bin/python
PORT     := 8000
DB_PATH  := duckdb/unified_data.duckdb

.PHONY: all setup download ingest normalize match views api eval validate clean help

# ─── Cible par défaut ────────────────────────────────────────────────────────
all: setup download ingest normalize match views
	@echo ""
	@echo "✅ Pipeline complet terminé. Lancez 'make api' pour démarrer le serveur."

# ─── Environnement virtuel & dépendances ─────────────────────────────────────
setup:
	@echo "🔧 Création de l'environnement virtuel..."
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip -q
	$(PIP) install -r requirements.txt -q
	@echo "✅ Environnement prêt."

# ─── Téléchargement des sources brutes ───────────────────────────────────────
download:
	@echo "📥 Téléchargement des sources brutes..."
	$(PYRUN) download.py

# ─── Phase 1 : Extraction CSV → Parquet ──────────────────────────────────────
# Correspond à 01_extract.py
ingest:
	@echo "📦 Phase 1 — Extraction (CSV → Parquet)..."
	$(PYRUN) etl/01_extract.py
	@echo "✅ Extraction terminée."

# ─── Phase 2 : Normalisation ─────────────────────────────────────────────────
# Correspond à 02_transform.py
normalize:
	@echo "🧹 Phase 2 — Normalisation (adresses, types, encodages)..."
	$(PYRUN) etl/02_transform.py
	@echo "✅ Normalisation terminée."

# ─── Phase 3 : Matching SIRENE ↔ RNA + Jointures BAN ────────────────────────
# Correspond à 03_load.py (jointures DuckDB + table golden_record)
match:
	@echo "🔗 Phase 3 — Matching SIRENE/RNA et jointure BAN (DuckDB)..."
	$(PYRUN) etl/03_load.py
	@echo "✅ Matching et chargement terminés."

# ─── Phase 4 : Génération des vues optimisées ────────────────────────────────
# Les vues (golden_record, search_index, stats_by_postal) sont créées dans 03_load.py
# Cette cible est un alias sémantique pour la cohérence avec le sujet
views: match
	@echo "📊 Vues déjà générées lors du chargement (golden_record, search_index, stats_by_postal)."

# ─── Validation de la base ───────────────────────────────────────────────────
validate:
	@echo "🔍 Validation de la base unifiée..."
	$(PYRUN) etl/04_validate.py

# ─── Lancement de l'API ──────────────────────────────────────────────────────
api:
	@echo "🚀 Démarrage de l'API sur http://0.0.0.0:$(PORT) ..."
	@echo "   Docs interactives : http://localhost:$(PORT)/docs"
	DB_PATH=$(DB_PATH) $(VENV)/bin/uvicorn api.api:app \
		--host 0.0.0.0 \
		--port $(PORT) \
		--workers 4 \
		--log-level info

# ─── Lancement des tests d'intégrité JSON ────────────────────────────────────
eval:
	@echo "🧪 Tests d'intégrité JSON (cas Gold)..."
	$(PYRUN) etl/04_validate.py

# ─── Nettoyage des fichiers générés ──────────────────────────────────────────
clean:
	@echo "🗑️  Nettoyage des fichiers générés..."
	rm -rf data_parquet/*.parquet
	rm -rf duckdb/unified_data.duckdb duckdb/search.db
	@echo "✅ data_parquet/ et duckdb/ nettoyés (data_raw conservé)."

# Nettoyage complet (y compris venv)
clean-all: clean
	rm -rf $(VENV)
	@echo "✅ Environnement virtuel supprimé."

# ─── Aide ────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════╗"
	@echo "║           ETL CHALLENGE — Commandes disponibles          ║"
	@echo "╠══════════════════════════════════════════════════════════╣"
	@echo "║  make setup      → Créer venv + installer requirements   ║"
	@echo "║  make download   → Télécharger les sources brutes        ║"
	@echo "║  make ingest     → Phase 1 : CSV → Parquet               ║"
	@echo "║  make normalize  → Phase 2 : Nettoyage & normalisation   ║"
	@echo "║  make match      → Phase 3 : Jointures DuckDB            ║"
	@echo "║  make views      → Alias de match (vues pré-calculées)   ║"
	@echo "║  make validate   → Vérification base + cas Gold          ║"
	@echo "║  make api        → Lancer le serveur FastAPI (port 8000) ║"
	@echo "║  make eval       → Tests d'intégrité JSON                ║"
	@echo "║  make all        → Pipeline complet (sans api)           ║"
	@echo "║  make clean      → Supprimer data_parquet/ et duckdb/     ║"
	@echo "║  make clean-all  → + supprimer le venv                   ║"
	@echo "╚══════════════════════════════════════════════════════════╝"
	@echo ""
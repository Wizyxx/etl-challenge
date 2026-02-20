.PHONY: install ingest normalize match index api eval clean all

# Variables
PYTHON   := venv/bin/python
UVICORN  := venv/bin/uvicorn
# CORRECTION : On pointe vers le bon dossier
DB_PATH  := data/processed/unified_data.duckdb
SQL_PATH := data/processed/search.db

# 0. Installation
install:
	$(PYTHON) -m pip install -r requirements.txt

# 1. Extraction
ingest:
	$(PYTHON) etl/01_extract.py

# 2. Transformation
normalize:
	$(PYTHON) etl/02_transform.py

# 3. Chargement (DuckDB)
match:
	$(PYTHON) etl/03_load.py

# 4. Indexation (SQLite FTS5) - INDISPENSABLE
index:
	$(PYTHON) etl/05_index_fts.py

# Pipeline complet
all: ingest normalize match index
	@echo "🚀 Pipeline terminé ! Prêt pour le stress-test."

# Lancement API (Correction des variables d'environnement)
api:
	@echo "🌍 Lancement de l'API..."
	export DB_PATH=$(DB_PATH) && \
	export SQLITE_PATH=$(SQL_PATH) && \
	$(UVICORN) api.main:app --host 0.0.0.0 --port 8000 --workers 4

# Validation
eval:
	$(PYTHON) etl/04_validate.py

clean:
	rm -rf data/processed/*.parquet
	rm -rf data/processed/*.duckdb
	rm -rf data/processed/*.db
	rm -rf duckdb/*
# ETL Challenge — Référentiel Unifié SIRENE × RNA × BAN

> Pipeline de traitement de données massives (~15 Go bruts) produisant une base unifiée
> des organisations en France, exposée via une API REST performante.

---

## Architecture

```
ETL-CHALLENGE/
├── api/
│   └── api.py                # API FastAPI — endpoints /siret, /search, /stats
├── data_raw/                 # Archives sources (.zip, .gz) — non commitées
├── data_parquet/             # Parquets intermédiaires (raw + clean)
├── duckdb/                   # Base DuckDB finale + SQLite FTS5
├── etl/
│   ├── 01_extract.py         # Phase 1 : CSV → Parquet (streaming, no OOM)
│   ├── 02_transform.py       # Phase 2 : Nettoyage, normalisation adresses
│   ├── 03_load.py            # Phase 3 : Jointures DuckDB, vues pré-calculées
│   └── 04_validate.py        # Phase 4 : Tests d'intégrité (cas Gold)
├── download_data.sh          # Téléchargement des sources brutes
├── Makefile.sh               # Orchestrateur
├── requirements.txt
└── README.md
```

### Stack technique

| Composant       | Technologie          | Justification                                      |
|-----------------|----------------------|----------------------------------------------------|
| Langage         | Python 3.10+         | Standard, écosystème data mature                   |
| Format données  | Parquet (Snappy)     | Lecture colonnaire rapide, compression efficace    |
| Moteur SQL      | DuckDB               | Jointures analytiques sur Parquet sans charger RAM |
| API             | FastAPI + Uvicorn    | Asynchrone, performant, OpenAPI auto-générée       |
| Orchestration   | Makefile             | Commandes standardisées et reproductibles          |

---

## Démarrage rapide

### Prérequis

- Python 3.10+
- `wget` installé
- ~60 Go d'espace disque (sources brutes + Parquet + DuckDB)

### Installation & pipeline complet

```bash
# 1. Cloner le projet
git clone <url_repo> && cd ETL-CHALLENGE

# 2. Tout en une commande (venv + dépendances + download + ETL complet)
make all

# 3. Lancer l'API
make api
```

L'API sera disponible sur `http://localhost:8000`.
Documentation interactive : `http://localhost:8000/docs`

### Commandes individuelles

```bash
make setup       # Créer venv + installer requirements
make download    # Télécharger les 4 sources brutes
make ingest      # Phase 1 : CSV → Parquet
make normalize   # Phase 2 : Nettoyage & normalisation
make match       # Phase 3 : Jointures DuckDB (golden_record)
make validate    # Vérifier la base (cas Gold + index)
make api         # Démarrer le serveur (port 8000)
make clean       # Supprimer data_parquet/ et duckdb/ (conserver data_raw)
```

---

## Sources de données

| Source | Fichier | Volume |
|--------|---------|--------|
| [SIRENE Établissements (INSEE)](https://www.data.gouv.fr/fr/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret/) | `StockEtablissement_utf8.zip` | ~4 Go |
| [SIRENE Unités Légales (INSEE)](https://www.data.gouv.fr/fr/datasets/base-sirene-des-entreprises-et-de-leurs-etablissements-siren-siret/) | `StockUniteLegale_utf8.zip` | ~1.5 Go |
| [RNA — Répertoire National des Associations](https://www.data.gouv.fr/fr/datasets/repertoire-national-des-associations/) | `rna_waldec.zip` | ~500 Mo |
| [BAN — Base Adresse Nationale](https://adresse.data.gouv.fr/donnees-nationales) | `adresses-france.csv.gz` | ~4 Go |

---

## Pipeline ETL

### Phase 1 — Extraction (`01_extract.py`)

Lecture **par chunks** des CSV compressés → conversion en **Parquet Snappy** sans jamais charger le fichier entier en RAM.

- SIRENE Établissements : ~35M lignes
- SIRENE Unités Légales : ~12M lignes (pour résoudre les noms)
- RNA : ~104 fichiers CSV fusionnés (~1.7M associations)
- BAN : ~50M adresses géolocalisées

### Phase 2 — Transformation (`02_transform.py`)

- Harmonisation des abréviations de type de voie (`AV` → `AVENUE`, `BD` → `BOULEVARD`…)
- Nettoyage des codes postaux (zfill, validation `^\d{5}$`)
- Validation des coordonnées GPS (filtrage hors `[-90,90] × [-180,180]`)
- Construction de la **clé de jointure BAN** : `{code_postal}_{numéro}{répétition}_{TYPE VOIE LIBELLÉ}`

### Phase 3 — Chargement & Jointures (`03_load.py`)

DuckDB opère directement sur les fichiers Parquet (zéro copie RAM) :

```
SIRENE ──┐
          ├─ LEFT JOIN → golden_record (table plate, clé : siret)
RNA ──────┤
          └─ LEFT JOIN
BAN ───────────────────┘
```

**Stratégie de jointure RNA :**
1. **Priorité** : `SIRENE.siret = RNA.siret` (14 chiffres exacts)
2. **Fallback** : `SIRENE.siren = RNA.siret[:9]` (SIREN du siège)

**Tables générées :**

| Table | Rôle | Index |
|-------|------|-------|
| `unified_records` | Golden record complet | `siret`, `siren`, `postal_code`, `name` |
| `search_index` | Recherche textuelle `LIKE` | `dept`, `postal_code` |
| `stats_by_postal` | Agrégats pré-calculés par CP | `postal_code` |

---

## API REST

Base URL : `http://<IP>:8000/api/v1`

### Endpoints

#### `GET /ping`
Healthcheck — répond en < 5 ms.
```json
{"status": "ok"}
```

#### `GET /siret/{siret}`
Fiche unifiée d'un établissement (SIRENE + RNA + BAN).

```bash
curl http://localhost:8000/api/v1/siret/77567227200020
```

```json
{
  "identity": {
    "siret": "77567227200020",
    "nom_raison_sociale": "CROIX ROUGE FRANCAISE",
    "enseigne": null,
    "categorie_entreprise": "PME"
  },
  "asso_id": {
    "id_rna": "W751000060",
    "date_publication_jo": "1901-07-01"
  },
  "location": {
    "numero_voie": "98",
    "type_voie": "RUE",
    "libelle_voie": "DIDOT",
    "code_postal": "75014",
    "commune": "PARIS",
    "geo_score": 0.98,
    "latitude": 48.8296,
    "longitude": 2.3235,
    "is_ban_validated": true
  },
  "status": "open",
  "nature": null
}
```

**Erreurs :**
- `400` — SIRET non numérique ou ≠ 14 chiffres
- `404` — SIRET inexistant en base

#### `GET /search?q=...&dept=...`
Recherche textuelle filtrée par département (retourne ≤ 10 résultats).

```bash
curl "http://localhost:8000/api/v1/search?q=boulangerie&dept=69"
```

```json
{
  "query": "boulangerie",
  "filter_dept": "69",
  "count": 7,
  "results": [
    {
      "siret": "88245112300015",
      "name": "BOULANGERIE DE L HOTEL DE VILLE",
      "is_association": false,
      "city": "LYON"
    }
  ]
}
```

Paramètres optionnels : `dept` (2 chiffres) ou `postal_code` (5 chiffres).

#### `GET /stats/{code_postal}`
Agrégats pré-calculés par code postal (< 50 ms grâce à la table pré-aggrégée).

```bash
curl http://localhost:8000/api/v1/stats/75013
```

```json
{
  "zone": "75013",
  "total_entites": 14502,
  "repartition": {
    "entreprises_pures": 11302,
    "associations": 3200,
    "etablissements_fermes": 2800
  },
  "top_naf": {
    "code": "6201Z",
    "libelle": null,
    "count": 312
  }
}
```

---

## Performance

### Objectifs (SLA stress test 500 requêtes)

| Endpoint | Cible p95 | Technique |
|----------|-----------|-----------|
| `/ping` | < 5 ms | Réponse statique |
| `/siret/{siret}` | < 200 ms | Index DuckDB sur `siret` |
| `/search` | < 500 ms | Index DuckDB sur `dept` + `LIKE` |
| `/stats/{cp}` | < 100 ms | Table pré-agrégée `stats_by_postal` |

### Pool de connexions

L'API utilise un pool de connexions DuckDB **thread-local** : chaque worker Uvicorn
obtient sa propre connexion `read_only`, évitant toute contention sur les 500 requêtes concurrentes.

### Activer le Ping ICMP (déduction latence réseau)

```bash
# Autoriser le ping entrant (requis pour le bonus < 500ms)
sudo ufw allow proto icmp
```

---

## Cas de test Gold

Ces deux SIRET sont utilisés par le correcteur pour valider les jointures :

| SIRET | Entité | Attendu |
|-------|--------|---------|
| `13002526500013` | Direction Interministérielle du Numérique (DINUM) | `status=open`, `is_ban_validated=true`, coordonnées GPS |
| `77567227200020` | Croix Rouge Française | `id_rna=W751000060`, coordonnées GPS |

Vérification rapide :
```bash
make validate
# ou
python etl/04_validate.py
```

---

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `DB_PATH` | `duckdb/unified_data.duckdb` | Chemin vers la base DuckDB |
| `PORT` | `8000` | Port d'écoute de l'API |

---

## Reproductibilité

```bash
# Installation propre depuis zéro
make clean-all
make all
make validate
make api
```

> ⚠️ Les fichiers `data_raw/` ne sont pas commités (`.gitignore`).
> Relancer `make download` pour les récupérer.
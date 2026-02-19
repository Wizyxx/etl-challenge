# Frontend - Référentiel Unifié (SIRENE × RNA × BAN)

Bienvenue dans le dépôt **Frontend** du projet *5 Days Challenge*.
Ce projet implémente une interface utilisateur (IHM) moderne, rapide et résiliente pour consulter la base de données unifiée des entreprises et associations françaises.

## Choix d'Architecture (Découplage)
Pour répondre aux exigences de performance (Stress Test) et de robustesse, nous avons opté pour une **architecture totalement découplée (Microservices)** :
- **Le Backend (API FastAPI + DuckDB)** est hébergé sur une Machine Virtuelle dédiée pour traiter la charge et répondre au Ping (ICMP).
- **Le Frontend (ce dépôt)** est une Single Page Application (SPA) statique et légère.

### Technologies utilisées :
- **HTML5 / CSS3** (Vanilla)
- **JavaScript** (Vanilla, Fetch API)
- **Bootstrap 5** (Design responsive via CDN)
- **Leaflet.js** (Cartographie interactive OpenStreetMap)
- **Chart.js / Progress Bars** (Dataviz)

---

## Comment lancer le projet en local ?

### Prérequis
Aucun ! Seul Python (déjà installé sur la plupart des machines) est requis pour lancer un mini-serveur local afin d'éviter les erreurs CORS du navigateur.

### Lancement rapide
1. Ouvrez un terminal à la racine de ce dossier.
2. Exécutez le script de lancement :
   ```bash
   bash run_frontend.sh
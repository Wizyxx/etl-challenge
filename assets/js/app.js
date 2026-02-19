/* global L, API_ENDPOINTS, apiCall */

/**
 * ══════════════════════════════════════════════════════════════════════
 * APP.JS — Logique Principale du Frontend
 * 5 Days Challenge — Référentiel Unifié
 * ══════════════════════════════════════════════════════════════════════
 *
 * RESPONSABILITÉS :
 * 1. Healthcheck API au démarrage
 * 2. Gestion de la recherche
 * 3. Affichage des résultats
 * 4. Chargement de la fiche détaillée
 * 5. Initialisation de la carte Leaflet
 * 6. Chargement des stats
 *
 * ══════════════════════════════════════════════════════════════════════
 */

// ═══════════════════════════════════════════════════════════════════════
// VARIABLES GLOBALES
// ═══════════════════════════════════════════════════════════════════════

let leafletMap = null;      // Instance de la carte Leaflet
let leafletMarker = null;   // Marqueur sur la carte
let currentResults = [];    // Résultats de la dernière recherche


// ═══════════════════════════════════════════════════════════════════════
// INITIALISATION AU CHARGEMENT DE LA PAGE
// ═══════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    console.log('Application démarrée');

    // 1. Initialiser le dark mode
    initTheme();

    // 2. Vérifier l'état de l'API (gestion de la promesse pour éviter le warning)
    checkBackendHealth().catch(err => console.error("Erreur init healthcheck:", err));

    // 3. Attacher les événements
    setupEventListeners();
});


// ═══════════════════════════════════════════════════════════════════════
// FONCTION 1 : HEALTHCHECK API
// ═══════════════════════════════════════════════════════════════════════

/**
 * Vérifie si l'API d'Adrien est accessible en appelant GET /ping
 * Met à jour le badge dans la navbar
 */
async function checkBackendHealth() {
    const statusBadge = document.getElementById('api-status');

    try {
        console.log('Healthcheck API...');
        const data = await apiCall(API_ENDPOINTS.PING);

        if (data.status === 'ok') {
            statusBadge.innerHTML = '<i class="fa-solid fa-circle-check me-1"></i>API: En ligne';
            statusBadge.className = 'badge bg-success';
            console.log('Backend opérationnel');
        } else {
            // Gestion directe de l'erreur sans throw local
            handleHealthError(statusBadge, 'Réponse invalide du serveur');
        }

    } catch (error) {
        handleHealthError(statusBadge, error.message);
    }
}

/**
 * Helper pour afficher l'erreur de santé (évite la duplication de code)
 */
function handleHealthError(badgeElement, message) {
    console.error('Impossible de joindre l\'API:', message);
    badgeElement.innerHTML = '<i class="fa-solid fa-circle-xmark me-1"></i>API: Hors ligne';
    badgeElement.className = 'badge bg-danger';
    badgeElement.title = `Erreur : ${message}\n\nVérifiez que le serveur tourne.`;

    showAlert('warning',
        'Backend inaccessible',
        `Impossible de contacter l'API. ${message}`
    );
}


// ═══════════════════════════════════════════════════════════════════════
// FONCTION 2 : GESTION DES ÉVÉNEMENTS
// ═══════════════════════════════════════════════════════════════════════

function setupEventListeners() {
    // Bouton recherche (page home)
    const btnSearchHome = document.getElementById('btn-search-home');
    const inputSearchHome = document.getElementById('search-input-home');
    const inputDeptHome = document.getElementById('dept-input-home');

    if (btnSearchHome) {
        btnSearchHome.addEventListener('click', () => {
            const query = inputSearchHome.value.trim();
            const dept = inputDeptHome.value.trim();
            handleSearch(query, dept).catch(console.error);
        });
    }

    // Touche Entrée sur les champs de recherche
    if (inputSearchHome) {
        inputSearchHome.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const query = inputSearchHome.value.trim();
                const dept = inputDeptHome.value.trim();
                handleSearch(query, dept).catch(console.error);
            }
        });
    }

    if (inputDeptHome) {
        inputDeptHome.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const query = inputSearchHome.value.trim();
                const dept = inputDeptHome.value.trim();
                handleSearch(query, dept).catch(console.error);
            }
        });
    }
    
    // Bouton toggle dark mode
    const toggleBtn = document.getElementById('theme-toggle');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleTheme);
    }
}


// ═══════════════════════════════════════════════════════════════════════
// FONCTION 3 : NAVIGATION ENTRE PAGES
// ═══════════════════════════════════════════════════════════════════════

function showHome() {
    document.getElementById('page-home').classList.remove('d-none');
    document.getElementById('page-results').classList.add('d-none');
}

function showResults() {
    document.getElementById('page-home').classList.add('d-none');
    document.getElementById('page-results').classList.remove('d-none');
}


// ═══════════════════════════════════════════════════════════════════════
// FONCTION 4 : RECHERCHE
// ═══════════════════════════════════════════════════════════════════════

/**
 * Lance une recherche via GET /search?q=...&dept=...
 * Affiche les résultats dans la liste de gauche
 * * @param {string} query - Terme de recherche (nom, enseigne, SIRET)
 * @param query
 * @param {string} dept - Code département ou postal (ex: "69" ou "69001")
 */
async function handleSearch(query, dept) {
    // 1. Nettoyage des entrées
    const q = query ? query.trim() : "";
    const d = dept ? dept.trim() : "";

    // 2. Validation : Recherche vide ou trop courte
    if (q.length < 3) {
        showAlert('warning', 'Recherche trop courte', 'Saisissez au moins 3 caractères (Nom ou SIRET).');
        return; // On arrête tout, pas d'appel API
    }

    // 3. Validation Spéciale : Si c'est des chiffres, est-ce un SIRET valide ?
    const isNumeric = /^\d+$/.test(q);
    if (isNumeric && q.length !== 14 && q.length !== 9) {
        // Si c'est numérique mais pas 9 (SIREN) ou 14 (SIRET) chiffres -> Erreur
        showAlert('warning', 'Format invalide', 'Un SIRET doit contenir exactement 14 chiffres.');
        return;
    }

    // 4. Validation Département (Doit être 2 ou 3 caractères max, ex: 69, 974, 2A)
    if (d && (d.length < 2 || d.length > 3)) {
        showAlert('warning', 'Département invalide', 'Le département doit faire 2 ou 3 caractères (ex: 69, 2A).');
        return;
    }

    console.log(`Recherche validée : "${q}" (dept: ${d || 'tous'})`);

    // Basculer vers la page résultats
    showResults();

    // UI : Afficher le loader
    const loader = document.getElementById('loading-spinner');
    const resultsList = document.getElementById('results-list');
    const resultsCount = document.getElementById('results-count');

    loader.classList.remove('d-none');
    resultsList.innerHTML = ''; // Clear
    resultsCount.textContent = 'Recherche en cours...';

    try {
        // Construction de l'URL avec paramètres
        const params = new URLSearchParams({ q: q });
        if (d) {
            params.append('dept', d);
        }

        const url = `${API_ENDPOINTS.SEARCH}?${params.toString()}`;

        // Appel API
        const data = await apiCall(url);

        // Succès API : Stocker et afficher
        currentResults = data.results || [];
        renderResults(data);

    } catch (error) {
        console.warn('API inaccessible, passage en mode DÉMO (Mock Data)');
        await new Promise(r => setTimeout(r, 500));

        const mockData = getMockData(q);
        currentResults = mockData.results;

        renderResults(mockData);

        // Petit toast pour prévenir que c'est du faux
        showAlert('info', 'Mode Démonstration', 'L\'API étant hors ligne, des données exemples sont affichées.');
    }
}


/**
 * Affiche les résultats de recherche dans la liste
 * * @param {object} data - Données retournées par /search (ou mock)
 */
function renderResults(data) {
    const loader = document.getElementById('loading-spinner');
    const resultsList = document.getElementById('results-list');
    const resultsCount = document.getElementById('results-count');

    loader.classList.add('d-none');

    const count = data.count || 0;
    const results = data.results || [];

    resultsCount.innerHTML = `
        <strong>${count}</strong> résultat${count > 1 ? 's' : ''} 
        pour « <em>${data.query || ''}</em> »
    `;

    if (count === 0 || results.length === 0) {
        resultsList.innerHTML = `
            <div class="list-group-item text-center text-muted py-5">
                <i class="fa-regular fa-face-frown fa-3x mb-3 opacity-50"></i><br>
                <strong>Aucun résultat trouvé</strong><br>
                <small>Essayez avec un terme différent ou un autre département.</small>
            </div>
        `;
        return;
    }

    resultsList.innerHTML = '';

    results.forEach((item, index) => {
        // Vérification stricte du flag is_association
        const isAsso = item.is_association === true;

        const card = document.createElement('div');
        card.className = 'list-group-item list-group-item-action result-item';
        card.dataset.index = index;

        // On prépare le HTML du badge pour qu'il soit bien visible
        // Rouge pour Asso, Bleu (ou rien) pour Entreprise
        const iconClass = isAsso ? 'fa-landmark text-danger' : 'fa-building text-primary';
        const badgeHtml = isAsso
            ? '<span class="badge bg-danger ms-2"><i class="fa-solid fa-landmark me-1"></i>Association</span>'
            : ''; // On n'affiche pas de badge "Entreprise" pour ne pas surcharger, ou on peut mettre un badge gris.

        card.innerHTML = `
            <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1">
                    <div class="d-flex align-items-center gap-2 mb-1">
                        <i class="fa-solid ${iconClass}"></i>
                        <h6 class="mb-0 fw-semibold">${item.name || '—'}</h6>
                        ${badgeHtml}
                    </div>
                    <small class="text-muted d-block">
                        <i class="fa-solid fa-location-dot me-1"></i>
                        ${item.city || 'Ville inconnue'}
                    </small>
                    <small class="text-muted font-monospace">${item.siret || ''}</small>
                </div>
                <i class="fa-solid fa-chevron-right text-muted"></i>
            </div>
        `;

        card.addEventListener('click', () => {
            document.querySelectorAll('.result-item').forEach(el => el.classList.remove('active'));
            card.classList.add('active');
            loadDetailedFiche(item.siret).catch(console.error);
        });

        resultsList.appendChild(card);
    });
}

/**
 * Génère des fausses données pour tester l'interface quand le backend dort.
 */
function getMockData(query) {
    return {
        count: 3,
        query: query,
        results: [
            {
                siret: "77567227200020",
                name: "CROIX ROUGE FRANCAISE",
                is_association: true,
                city: "PARIS 14 (75)",
                lat: 48.8296, lon: 2.3235
            },
            {
                siret: "44312012000015",
                name: "LA PETITE BOULANGERIE",
                is_association: false,
                city: "LYON (69)",
                lat: 45.7640, lon: 4.8357
            },
            {
                siret: "13002526500013",
                name: "DIRECTION INTERMINISTERIELLE DU NUMERIQUE",
                is_association: false,
                city: "PARIS 7 (75)",
                lat: 48.8507, lon: 2.3086
            }
        ]
    };
}

/**
 * Génère une fausse fiche détaillée pour le mode Démo
 * Respecte la structure JSON attendue par l'API (identity, location, asso_id)
 */
function getMockFiche(siret) {
    // 1. Cas Croix Rouge (Association)
    if (siret === "77567227200020") {
        return {
            status: "open",
            identity: {
                siret: "77567227200020",
                nom_raison_sociale: "CROIX ROUGE FRANCAISE",
                enseigne: "CRF",
                categorie_entreprise: "PME"
            },
            asso_id: {
                id_rna: "W751000060",
                date_publication_jo: "1901-07-01"
            },
            location: {
                numero_voie: "98",
                type_voie: "RUE",
                libelle_voie: "DIDOT",
                code_postal: "75014",
                commune: "PARIS",
                is_ban_validated: true,
                latitude: 48.8296,
                longitude: 2.3235
            }
        };
    }

    // 2. Cas Boulangerie (Entreprise standard à Lyon)
    if (siret === "44312012000015") {
        return {
            status: "open",
            identity: {
                siret: "44312012000015",
                nom_raison_sociale: "LA PETITE BOULANGERIE",
                enseigne: "AU BON PAIN",
                categorie_entreprise: "PME"
            },
            asso_id: null,
            location: {
                numero_voie: "12",
                type_voie: "RUE",
                libelle_voie: "DE LA REPUBLIQUE",
                code_postal: "69002",
                commune: "LYON",
                is_ban_validated: true,
                latitude: 45.7640,
                longitude: 4.8357
            }
        };
    }

    // 3. Cas DINUM (Administration)
    if (siret === "13002526500013") {
        return {
            status: "open",
            identity: {
                siret: "13002526500013",
                nom_raison_sociale: "DIRECTION INTERMINISTERIELLE DU NUMERIQUE",
                enseigne: "DINUM",
                categorie_entreprise: "ETI"
            },
            asso_id: null,
            location: {
                numero_voie: "20",
                type_voie: "AVENUE",
                libelle_voie: "DE SEGUR",
                code_postal: "75007",
                commune: "PARIS",
                is_ban_validated: true,
                latitude: 48.8507,
                longitude: 2.3086
            }
        };
    }

    // Fallback par défaut
    return null;
}


// ═══════════════════════════════════════════════════════════════════════
// FONCTION 5 : CHARGEMENT FICHE DÉTAILLÉE
// ═══════════════════════════════════════════════════════════════════════

/**
 * Charge la fiche complète d'un établissement via GET /siret/{siret}
 * Gère le fallback sur des données factices si l'API est hors ligne.
 * * @param {string} siret - Numéro SIRET (14 chiffres)
 */
async function loadDetailedFiche(siret) {
    if (!siret) return;

    console.log(`Chargement fiche : ${siret}`);

    const titleEl = document.getElementById('detail-title');
    if (titleEl) titleEl.textContent = "Chargement en cours...";

    const detailCard = document.getElementById('detail-card');
    const placeholder = document.getElementById('detail-placeholder');
    if (detailCard) detailCard.classList.remove('d-none');
    if (placeholder) placeholder.classList.add('d-none');

    let data;

    try {
        data = await apiCall(API_ENDPOINTS.SIRET(siret));

    } catch (error) {
        console.warn('API inaccessible pour le détail, passage en mode DÉMO (Mock Data)');

        await new Promise(r => setTimeout(r, 300));

        data = getMockFiche(siret);

        if (!data) {
            console.error('Erreur : Aucune donnée mockée pour ce SIRET');
            showAlert('danger', 'Erreur', 'Impossible de charger la fiche (API hors ligne et pas de données de test).');
            return;
        }

        showAlert('info', 'Mode Démo', 'Visualisation avec des données de test (API hors ligne).');
    }

    if (data) {
        renderDetailedFiche(data);
        if (data.location && data.location.latitude && data.location.longitude) {
            updateMap(
                data.location.latitude,
                data.location.longitude,
                data.identity.nom_raison_sociale || 'Établissement'
            );
        }
    }
}


/**
 * Affiche les données de la fiche dans la carte de droite
 *
 * @param {object} data - Données retournées par /siret/{siret}
 */
function renderDetailedFiche(data) {
    // Masquer le placeholder, afficher la fiche
    document.getElementById('detail-placeholder').classList.add('d-none');
    document.getElementById('detail-card').classList.remove('d-none');

    const identity = data.identity || {};
    const location = data.location || {};
    const assoId = data.asso_id || null;

    // Header : Nom + Badges
    document.getElementById('detail-title').textContent = identity.nom_raison_sociale || '—';
    document.getElementById('detail-enseigne').textContent = identity.enseigne
        ? `Enseigne : ${identity.enseigne}`
        : '';

    // Badge statut
    const statusBadge = document.getElementById('detail-status-badge');
    if (data.status === 'open') {
        statusBadge.textContent = 'ACTIF';
        statusBadge.className = 'badge bg-success';
    } else {
        statusBadge.textContent = 'FERMÉ';
        statusBadge.className = 'badge bg-secondary';
    }

    // Badge association (affiché uniquement si asso_id non null)
    const assoBadge = document.getElementById('detail-asso-badge');
    if (assoId && assoId.id_rna) {
        assoBadge.classList.remove('d-none');
    } else {
        assoBadge.classList.add('d-none');
    }

    // Bloc RNA (si association)
    const rnaBlock = document.getElementById('detail-rna-block');
    if (assoId && assoId.id_rna) {
        rnaBlock.classList.remove('d-none');
        document.getElementById('detail-rna-id').textContent = assoId.id_rna;
        document.getElementById('detail-rna-date').textContent = assoId.date_publication_jo
            ? `Publication JO : ${assoId.date_publication_jo}`
            : '';
    } else {
        rnaBlock.classList.add('d-none');
    }

    // Infos légales
    document.getElementById('detail-siret').textContent = identity.siret || '—';
    document.getElementById('detail-categorie').textContent = identity.categorie_entreprise || '—';
    document.getElementById('detail-status-text').innerHTML = data.status === 'open'
        ? '<span class="text-success"><i class="fa-solid fa-circle-check me-1"></i>Actif</span>'
        : '<span class="text-secondary"><i class="fa-solid fa-circle-xmark me-1"></i>Fermé</span>';
    document.getElementById('detail-enseigne-full').textContent = identity.enseigne || '—';

    // Localisation
    document.getElementById('detail-address').textContent = [
        location.numero_voie,
        location.type_voie,
        location.libelle_voie
    ].filter(Boolean).join(' ') || '—';
    document.getElementById('detail-postal').textContent = location.code_postal || '—';
    document.getElementById('detail-city').textContent = location.commune || '—';

    // Validation BAN
    const banValid = document.getElementById('detail-ban-valid');
    if (location.is_ban_validated) {
        banValid.innerHTML = '<span class="text-success"><i class="fa-solid fa-circle-check me-1"></i>Validé BAN</span>';
    } else {
        banValid.innerHTML = '<span class="text-muted"><i class="fa-solid fa-circle-xmark me-1"></i>Non validé</span>';
    }

    // Pré-remplir le code postal dans le widget stats
    if (location.code_postal) {
        document.getElementById('stats-cp-input').value = location.code_postal;
        document.getElementById('stats-widget').classList.remove('d-none');

        // Charger automatiquement les stats
        loadStats(location.code_postal).catch(console.error);
    }
}


// ═══════════════════════════════════════════════════════════════════════
// FONCTION 6 : CARTE LEAFLET
// ═══════════════════════════════════════════════════════════════════════

/**
 * Initialise la carte Leaflet (appelée au premier affichage d'une fiche)
 * Centre par défaut sur la France.
 */
function initMap() {
    if (leafletMap) return;

    console.log('Initialisation carte Leaflet');

    leafletMap = L.map('map', {
        center: [46.603354, 1.888334],
        zoom: 5,
        zoomControl: true,
        attributionControl: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap France | &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(leafletMap);
}


/**
 * Met à jour la carte avec un nouveau marqueur et centre la vue
 * @param {number} lat - Latitude
 * @param {number} lon - Longitude
 * @param {string} label - Label du popup (Nom de l'entreprise)
 */
function updateMap(lat, lon, label) {
    const detailCard = document.getElementById('detail-card');
    const placeholder = document.getElementById('detail-placeholder');

    if (detailCard && detailCard.classList.contains('d-none')) {
        detailCard.classList.remove('d-none');
        if (placeholder) placeholder.classList.add('d-none');
    }

    if (!leafletMap) {
        initMap();
    }
    leafletMap.invalidateSize();

    if (!lat || !lon || isNaN(lat) || isNaN(lon)) {
        console.warn("Coordonnées invalides pour la carte");
        return;
    }

    console.log(`Marqueur placé : ${lat}, ${lon}`);

    if (leafletMarker) {
        leafletMap.removeLayer(leafletMarker);
    }

    const defaultIcon = L.icon({
        iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
    });

    leafletMarker = L.marker([lat, lon], { icon: defaultIcon })
        .addTo(leafletMap)
        .bindPopup(`
            <div style="text-align: center;">
                <strong>${label}</strong><br/>
                <small>${lat.toFixed(5)}, ${lon.toFixed(5)}</small>
            </div>
        `);

    try {
        leafletMap.flyTo([lat, lon], 16, {
            duration: 1.5,
            easeLinearity: 0.25
        });
    } catch (e) {
        leafletMap.setView([lat, lon], 16);
    }

    setTimeout(() => {
        if (leafletMarker) leafletMarker.openPopup();
    }, 1500);

    const coordsDiv = document.getElementById('map-coords');
    if (coordsDiv) {
        coordsDiv.innerHTML = `
            <i class="fa-solid fa-location-dot me-1 text-primary"></i>
            Lat: <strong>${lat.toFixed(5)}</strong> · Lon: <strong>${lon.toFixed(5)}</strong>
        `;
    }
}


// ═══════════════════════════════════════════════════════════════════════
// FONCTION 7 : STATISTIQUES
// ═══════════════════════════════════════════════════════════════════════

/**
 * Charge les statistiques pour un code postal via GET /stats/{cp}
 * Affiche les barres de progression dans le widget
 * Gère le fallback sur des données factices si l'API est hors ligne.
 * * @param {string} cpOverride - Code postal (si fourni, sinon lit le champ input)
 */
async function loadStats(cpOverride) {
    // 1. Récupération du CP (priorité à l'argument, sinon l'input)
    const cpInput = document.getElementById('stats-cp-input');
    const cpVal = cpOverride || (cpInput ? cpInput.value.trim() : '');

    // 2. VALIDATION STRICTE CODE POSTAL
    // Code postal doit être exactement 5 chiffres (Regex: /^\d{5}$/)
    if (!/^\d{5}$/.test(cpVal)) {
        // On n'affiche l'alerte que si c'est une action utilisateur explicite (clic bouton)
        // Si c'est un chargement auto depuis une fiche (cpOverride), on ignore silencieusement
        if (!cpOverride && cpVal.length > 0) {
            showAlert('warning', 'Code Postal invalide', 'Veuillez saisir exactement 5 chiffres (ex: 75001).');
        }
        return;
    }

    console.log(`Chargement stats pour : ${cpVal}`);

    // UI : Afficher le widget s'il est caché
    const widget = document.getElementById('stats-widget');
    if (widget) widget.classList.remove('d-none');

    try {
        // 2. TENTATIVE API RÉELLE
        const data = await apiCall(API_ENDPOINTS.STATS(cpVal));

        // Succès
        renderStats(data);

    } catch (error) {
        console.warn('API Stats inaccessible, passage en mode DÉMO (Mock Data)');

        // 3. FALLBACK MODE DÉMO
        // On simule une petite latence
        await new Promise(r => setTimeout(r, 400));

        // On génère des fausses stats cohérentes avec le CP
        const mockData = getMockStats(cpVal);

        renderStats(mockData);
    }
}

/**
 * Génère des stats fictives pour le mode démo.
 * Calcule des chiffres basés sur le CP pour que ce soit stable.
 */
function getMockStats(cp) {
    // On utilise le CP comme "graine" pour avoir toujours les mêmes chiffres pour le même CP
    const seed = parseInt(cp) || 75000;
    const total = (seed % 1000) * 15 + 500; // Total entre 500 et 15500

    return {
        zone: cp,
        total_entites: total,
        repartition: {
            entreprises_pures: Math.floor(total * 0.85),
            associations: Math.floor(total * 0.15),
            etablissements_fermes: Math.floor(total * 0.2) // ~20% de fermés
        },
        top_naf: {
            code: "56.10A",
            libelle: "Restauration traditionnelle",
            count: Math.floor(total * 0.08)
        }
    };
}

/**
 * Affiche les statistiques dans le widget
 * @param {object} data - Données retournées par /stats/{cp}
 */
function renderStats(data) {
    const statsContent = document.getElementById('stats-content');
    if (statsContent) statsContent.classList.remove('d-none');

    const rep = data.repartition || {};

    // Base de calcul pour les pourcentages (Total global ou somme des parties)
    const totalActif = (rep.entreprises_pures || 0) + (rep.associations || 0);
    const base = totalActif > 0 ? totalActif : (data.total_entites || 1);

    // Calcul des pourcentages
    const pctCompanies = Math.round(((rep.entreprises_pures || 0) / base) * 100);
    const pctAsso = Math.round(((rep.associations || 0) / base) * 100);
    // Pour les fermés, c'est souvent un ratio par rapport au total historique
    const pctClosed = Math.round(((rep.etablissements_fermes || 0) / (data.total_entites || base)) * 100);

    // Mise à jour des barres via une fonction helper
    updateStatBar('bar-companies', 'val-companies', pctCompanies, rep.entreprises_pures);
    updateStatBar('bar-asso', 'val-asso', pctAsso, rep.associations);
    updateStatBar('bar-closed', 'val-closed', pctClosed, rep.etablissements_fermes);

    // Top NAF
    const topNaf = data.top_naf || {};
    const nafCodeEl = document.getElementById('top-naf-code');
    const nafCountEl = document.getElementById('top-naf-count');

    if (nafCodeEl) nafCodeEl.textContent = topNaf.code ? `${topNaf.code} - ${topNaf.libelle || ''}` : 'Non disponible';
    if (nafCountEl) nafCountEl.textContent = topNaf.count ? `${formatNumber(topNaf.count)} établissements` : '';
}

/**
 * Helper pour mettre à jour une barre de progression (Largeur + Texte)
 */
function updateStatBar(barId, valId, percent, value) {
    const bar = document.getElementById(barId);
    const val = document.getElementById(valId);

    if (bar) {
        bar.style.width = `${Math.min(percent, 100)}%`;
        bar.setAttribute('aria-valuenow', String(percent));
    }
    if (val) {
        val.textContent = formatNumber(value || 0);
    }
}


// ═══════════════════════════════════════════════════════════════════════
// UTILITAIRES
// ═══════════════════════════════════════════════════════════════════════

/**
 * Affiche une alerte Bootstrap en haut de page
 *
 * @param {string} type - Type d'alerte ('success', 'warning', 'danger', 'info')
 * @param {string} title - Titre de l'alerte
 * @param {string} message - Message détaillé
 */
function showAlert(type, title, message) {
    // Créer l'alerte
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3`;
    alert.style.zIndex = '9999';
    alert.style.minWidth = '400px';
    alert.innerHTML = `
        <strong>${title}</strong><br>
        <small>${message}</small>
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(alert);

    // Auto-dismiss après 5 secondes
    setTimeout(() => {
        alert.remove();
    }, 5000);
}


/**
 * Formate un nombre avec séparateurs de milliers
 *
 * @param {number} n - Nombre à formater
 * @returns {string} - Nombre formaté (ex: "1 234 567")
 */
function formatNumber(n) {
    if (!n && n !== 0) return '—';
    return n.toLocaleString('fr-FR');
}


/**
 * Fonction helper pour pré-remplir la recherche depuis les suggestions
 *
 * @param {string} query - Terme de recherche
 * @param {string} dept - Département
 */
function fillSearchHome(query, dept) {
    document.getElementById('search-input-home').value = query;
    document.getElementById('dept-input-home').value = dept;
    handleSearch(query, dept).catch(console.error);
}


// ═══════════════════════════════════════════════════════════════════════
// GESTION DU DARK MODE
// ═══════════════════════════════════════════════════════════════════════

/**
 * Initialise le thème au chargement de la page
 * Ordre de priorité :
 * 1. Préférence sauvegardée dans localStorage
 * 2. Préférence système (prefers-color-scheme)
 * 3. Light par défaut
 */
function initTheme() {
    const toggleBtn = document.getElementById('theme-toggle');
    
    // Récupérer la préférence sauvegardée
    let savedTheme = localStorage.getItem('theme');

    // Si pas de préférence sauvegardée, vérifier la préférence système
    if (!savedTheme) {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        savedTheme = prefersDark ? 'dark' : 'light';
    }

    // Appliquer le thème
    applyTheme(savedTheme);

    // Mettre à jour l'icône
    updateThemeIcon(savedTheme);

    // Attacher l'événement click sur le bouton toggle
    toggleBtn.addEventListener('click', toggleTheme);

    // Écouter les changements de préférence système (optionnel)
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        // Ne changer que si l'utilisateur n'a pas de préférence explicite
        if (!localStorage.getItem('theme')) {
            const newTheme = e.matches ? 'dark' : 'light';
            applyTheme(newTheme);
            updateThemeIcon(newTheme);
        }
    });

    console.log(`Thème initialisé : ${savedTheme}`);
}


/**
 * Bascule entre light et dark
 */
function toggleTheme() {
    const currentTheme = document.body.getAttribute('data-theme');
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';

    applyTheme(newTheme);
    updateThemeIcon(newTheme);

    // Sauvegarder la préférence
    localStorage.setItem('theme', newTheme);

    console.log(`Thème changé : ${currentTheme} → ${newTheme}`);
}


/**
 * Applique le thème (modifie l'attribut data-theme sur <body>)
 *
 * @param {string} theme - 'light' ou 'dark'
 */
function applyTheme(theme) {
    document.body.setAttribute('data-theme', theme);

    // Mettre à jour la classe bg-light du body pour Bootstrap
    if (theme === 'dark') {
        document.body.classList.remove('bg-white'); // Correction ici aussi
        document.body.classList.remove('bg-light');
        document.body.classList.add('bg-dark');
    } else {
        document.body.classList.remove('bg-dark');
        document.body.classList.add('bg-white'); // Correction pour utiliser bg-white
    }
}


/**
 * Met à jour l'icône du bouton toggle (lune/soleil)
 *
 * @param {string} theme - 'light' ou 'dark'
 */
function updateThemeIcon(theme) {
    const toggleIcon = document.querySelector('#theme-toggle i');

    if (theme === 'dark') {
        // Afficher l'icône soleil (on est en dark, clic → light)
        toggleIcon.className = 'fa-solid fa-sun';
    } else {
        // Afficher l'icône lune (on est en light, clic → dark)
        toggleIcon.className = 'fa-solid fa-moon';
    }
}


// ═══════════════════════════════════════════════════════════════════════
// FIN DU FICHIER
// ═══════════════════════════════════════════════════════════════════════

console.log('app.js chargé et prêt');

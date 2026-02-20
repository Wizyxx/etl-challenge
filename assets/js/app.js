/* global L, API_ENDPOINTS, apiCall */

/**
 * ══════════════════════════════════════════════════════════════════════
 * APP.JS — Logique Principale du Frontend
 * 5 Days Challenge — Référentiel Unifié SIRENE × RNA × BAN
 * Version finale — Alignée sur le backend FastAPI
 * ══════════════════════════════════════════════════════════════════════
 *
 * FORMAT API RÉEL (backend FastAPI) :
 *
 * GET /ping → { "status": "ok" }
 *
 * GET /siret/{siret} → {
 *   siret, rna, name, status, nature,
 *   address: { number, street, postal_code, city,
 *              is_ban_validated, latitude, longitude }
 * }
 *
 * GET /search?q=...&dept=...&postal_code=... → {
 *   query, filter_dept, count,
 *   results: [{ siret, name, address_city, is_association }]
 * }
 *
 * GET /stats/{cp} → {
 *   zone, total_entites,
 *   repartition: { entreprises_pures, associations, etablissements_fermes },
 *   top_naf: { code, libelle, count }
 * }
 *
 * Erreurs standardisées :
 *   404 → { "error": "Siret not found", "input": "..." }
 *   400 → { "error": "INVALID_FORMAT", "message": "..." }
 *
 * ══════════════════════════════════════════════════════════════════════
 */


// ═══════════════════════════════════════════════════════════════════════
// VARIABLES GLOBALES
// ═══════════════════════════════════════════════════════════════════════

let leafletMap    = null;   // Instance Leaflet (singleton)
let leafletMarker = null;   // Marqueur courant
let currentResults = [];   // Résultats de la dernière recherche


// ═══════════════════════════════════════════════════════════════════════
// INITIALISATION
// ═══════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    console.log('App démarrée — Référentiel Unifié v3');
    initTheme();
    checkBackendHealth().catch(err => console.error('Healthcheck échoué:', err));
    setupEventListeners();
});


// ═══════════════════════════════════════════════════════════════════════
// HEALTHCHECK
// ═══════════════════════════════════════════════════════════════════════

async function checkBackendHealth() {
    const statusBadge = document.getElementById('api-status');
    try {
        const data = await apiCall(API_ENDPOINTS.PING);
        if (data.status === 'ok') {
            statusBadge.innerHTML = '<i class="fa-solid fa-circle-check me-1"></i>API: En ligne';
            statusBadge.className = 'badge bg-success';
        } else {
            throw new Error('Réponse inattendue du serveur');
        }
    } catch (error) {
        statusBadge.innerHTML = '<i class="fa-solid fa-circle-xmark me-1"></i>API: Hors ligne';
        statusBadge.className = 'badge bg-danger';
        statusBadge.title = `Erreur : ${error.message}`;
        console.warn('API inaccessible:', error.message);
    }
}


// ═══════════════════════════════════════════════════════════════════════
// ÉVÉNEMENTS
// ═══════════════════════════════════════════════════════════════════════

function setupEventListeners() {
    // ── Page Home ──
    const btnHome    = document.getElementById('btn-search-home');
    const inputHome  = document.getElementById('search-input-home');
    const deptHome   = document.getElementById('dept-input-home');
    const toggleBtn  = document.getElementById('theme-toggle');

    const triggerHome = () => {
        handleSearch(inputHome.value.trim(), deptHome.value.trim()).catch(console.error);
    };

    if (btnHome) btnHome.addEventListener('click', triggerHome);
    [inputHome, deptHome].forEach(el => {
        if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') triggerHome(); });
    });

    // ── Page Résultats (barre de re-recherche) ──
    const btnResults  = document.getElementById('btn-search-results');
    const inputResults = document.getElementById('search-input-results');
    const deptResults  = document.getElementById('dept-input-results');

    const triggerResults = () => {
        const q = inputResults ? inputResults.value.trim() : '';
        const d = deptResults  ? deptResults.value.trim()  : '';
        handleSearch(q, d).catch(console.error);
    };

    if (btnResults) btnResults.addEventListener('click', triggerResults);
    [inputResults, deptResults].forEach(el => {
        if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') triggerResults(); });
    });

    // ── Stats ──
    const cpInput = document.getElementById('stats-cp-input');
    if (cpInput) {
        cpInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') loadStats().catch(console.error);
        });
    }

    // ── Theme toggle ──
    if (toggleBtn) toggleBtn.addEventListener('click', toggleTheme);
}


// ═══════════════════════════════════════════════════════════════════════
// NAVIGATION — showHome() avec CLEAN STATE complet
// ═══════════════════════════════════════════════════════════════════════

function showHome() {
    // 1. Afficher Home, masquer Résultats
    document.getElementById('page-home').classList.remove('d-none');
    document.getElementById('page-results').classList.add('d-none');

    // 2. Vider les champs de recherche de la HOME
    const homeInput = document.getElementById('search-input-home');
    const homeDept  = document.getElementById('dept-input-home');
    if (homeInput) homeInput.value = '';
    if (homeDept)  homeDept.value  = '';

    // 3. Focus sur le champ de recherche
    setTimeout(() => { if (homeInput) homeInput.focus(); }, 100);

    // 4. Réinitialiser l'état complet de la page résultats
    resetResultsState();

    // 5. Réinitialiser la carte Leaflet (sans la détruire — juste recentrer sur la France)
    resetMap();
}

/**
 * Remet la page résultats dans son état initial :
 * liste vide, fiche masquée, placeholder visible, stats cachées
 */
function resetResultsState() {
    currentResults = [];

    // Compteur
    const countEl = document.getElementById('results-count');
    if (countEl) countEl.textContent = 'Résultats de recherche';

    // Liste résultats → placeholder
    const resultsList = document.getElementById('results-list');
    if (resultsList) {
        resultsList.innerHTML = `
            <div class="list-group-item text-center text-muted py-5">
                <i class="fa-regular fa-folder-open fa-3x mb-3 opacity-50"></i><br>
                Lancez une recherche pour voir les résultats.
            </div>
        `;
    }

    // Masquer spinner
    const spinner = document.getElementById('loading-spinner');
    if (spinner) spinner.classList.add('d-none');

    // Masquer fiche détaillée, afficher placeholder
    document.getElementById('detail-card').classList.add('d-none');
    document.getElementById('detail-placeholder').classList.remove('d-none');

    // Masquer widget stats
    const statsWidget = document.getElementById('stats-widget');
    if (statsWidget) statsWidget.classList.add('d-none');

    // Vider la barre de re-recherche de la page résultats
    const inputResults = document.getElementById('search-input-results');
    const deptResults  = document.getElementById('dept-input-results');
    if (inputResults) inputResults.value = '';
    if (deptResults)  deptResults.value  = '';

    // Reset des champs de la fiche
    resetDetailCard();
}

/**
 * Vide tous les champs de la fiche Golden Record
 */
function resetDetailCard() {
    const fields = [
        'detail-title', 'detail-enseigne', 'detail-siret',
        'detail-categorie', 'detail-status-text', 'detail-enseigne-full',
        'detail-address', 'detail-postal', 'detail-city',
        'detail-ban-valid', 'detail-rna-id', 'detail-rna-date',
        'map-coords', 'top-naf-code', 'top-naf-count',
        'val-companies', 'val-asso', 'val-closed',
    ];
    fields.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '—';
    });

    // Reset badge statut
    const statusBadge = document.getElementById('detail-status-badge');
    if (statusBadge) { statusBadge.textContent = ''; statusBadge.className = 'badge'; }

    // Masquer badge asso et bloc RNA
    document.getElementById('detail-asso-badge')?.classList.add('d-none');
    document.getElementById('detail-rna-block')?.classList.add('d-none');

    // Reset barres de stats
    ['bar-companies', 'bar-asso', 'bar-closed'].forEach(id => {
        const bar = document.getElementById(id);
        if (bar) { bar.style.width = '0%'; bar.setAttribute('aria-valuenow', '0'); }
    });

    const statsContent = document.getElementById('stats-content');
    if (statsContent) statsContent.classList.add('d-none');
}

/**
 * Recentre la carte sur la France sans la détruire
 */
function resetMap() {
    if (leafletMap) {
        // Supprimer le marqueur
        if (leafletMarker) {
            leafletMap.removeLayer(leafletMarker);
            leafletMarker = null;
        }
        // Recentrer sur la France
        try {
            leafletMap.setView([46.603354, 1.888334], 5);
        } catch (e) {
            console.warn('resetMap: impossible de recentrer', e);
        }
    }

    const coordsDiv = document.getElementById('map-coords');
    if (coordsDiv) {
        coordsDiv.innerHTML = '<i class="fa-solid fa-location-dot me-1"></i>Coordonnées : —';
    }
}

function showResults() {
    document.getElementById('page-home').classList.add('d-none');
    document.getElementById('page-results').classList.remove('d-none');
}


// ═══════════════════════════════════════════════════════════════════════
// RECHERCHE
// GET /search?q=...&dept=...  ou  &postal_code=...
// Réponse : { query, filter_dept, count, results: [{siret, name, address_city, is_association}] }
// ═══════════════════════════════════════════════════════════════════════

async function handleSearch(query, dept) {
    const q = (query || '').trim();
    const d = (dept  || '').trim();

    if (q.length < 2) {
        showAlert('warning', 'Recherche trop courte', 'Saisissez au moins 2 caractères.');
        return;
    }

    // Si numérique : forcer SIRET 14 chiffres ou SIREN 9 chiffres
    if (/^\d+$/.test(q) && q.length !== 14 && q.length !== 9) {
        showAlert('warning', 'Format invalide', 'Un SIRET doit contenir 14 chiffres, un SIREN 9 chiffres.');
        return;
    }

    // Basculer vers la page résultats
    showResults();

    const loader       = document.getElementById('loading-spinner');
    const resultsList  = document.getElementById('results-list');
    document.getElementById('results-count');
    loader.classList.remove('d-none');
    resultsList.innerHTML = '';

    // Pré-remplir la barre de re-recherche
    const inputResults = document.getElementById('search-input-results');
    const deptResults  = document.getElementById('dept-input-results');
    if (inputResults) inputResults.value = q;
    if (deptResults)  deptResults.value  = d;

    // Réinitialiser la fiche à droite
    document.getElementById('detail-card').classList.add('d-none');
    document.getElementById('detail-placeholder').classList.remove('d-none');
    document.getElementById('stats-widget').classList.add('d-none');

    try {
        // Construction des paramètres
        const params = new URLSearchParams({ q });
        if (d) {
            // 5 chiffres → code postal ; sinon → département
            if (/^\d{5}$/.test(d)) {
                params.append('postal_code', d);
            } else {
                params.append('dept', d);
            }
        }

        const data = await apiCall(`${API_ENDPOINTS.SEARCH}?${params.toString()}`);
        currentResults = data.results || [];
        renderResults(data);

    } catch (error) {
        console.warn('API /search inaccessible, mode DÉMO:', error.message);
        await new Promise(r => setTimeout(r, 400));
        const mockData = getMockSearchData(q);
        currentResults = mockData.results;
        renderResults(mockData);
        showAlert('info', 'Mode Démonstration', 'API hors ligne — données de test affichées.');
    }
}

/**
 * Affiche les résultats dans la liste gauche.
 */
function renderResults(data) {
    const loader       = document.getElementById('loading-spinner');
    const resultsList  = document.getElementById('results-list');
    const resultsCount = document.getElementById('results-count');

    loader.classList.add('d-none');

    const count   = data.count   || 0;
    const results = data.results || [];

    resultsCount.innerHTML = `
        <strong>${count}</strong> résultat${count > 1 ? 's' : ''}
        pour « <em>${escapeHtml(data.query || '')}</em> »
    `;

    if (count === 0 || results.length === 0) {
        resultsList.innerHTML = `
            <div class="list-group-item text-center text-muted py-5">
                <i class="fa-regular fa-face-frown fa-3x mb-3 opacity-50"></i><br>
                <strong>Aucun résultat trouvé</strong><br>
                <small>Essayez un terme différent ou modifiez le filtre géographique.</small>
            </div>
        `;
        return;
    }

    resultsList.innerHTML = '';

    results.forEach((item, index) => {
        const isAsso = item.is_association === true;
        const cityLabel = item.address_city || item.city || '—';

        const iconClass  = isAsso ? 'fa-landmark text-danger' : 'fa-building text-primary';
        const badgeHtml  = isAsso
            ? '<span class="badge bg-danger ms-2"><i class="fa-solid fa-landmark me-1"></i>Association</span>'
            : '<span class="badge bg-primary ms-2"><i class="fa-solid fa-building me-1"></i>Entreprise</span>';

        const card = document.createElement('div');
        card.className = 'list-group-item list-group-item-action result-item';
        card.dataset.index = index;
        card.innerHTML = `
            <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1 min-w-0">
                    <div class="d-flex align-items-center gap-2 mb-1 flex-wrap">
                        <i class="fa-solid ${iconClass} flex-shrink-0"></i>
                        <h6 class="mb-0 fw-semibold text-truncate">${escapeHtml(item.name || '—')}</h6>
                        ${badgeHtml}
                    </div>
                    <small class="text-muted d-block">
                        <i class="fa-solid fa-location-dot me-1"></i>${escapeHtml(cityLabel)}
                    </small>
                    <small class="text-muted font-monospace">${item.siret || ''}</small>
                </div>
                <i class="fa-solid fa-chevron-right text-muted ms-2 flex-shrink-0"></i>
            </div>
        `;

        card.addEventListener('click', () => {
            // Highlight sélection
            document.querySelectorAll('.result-item').forEach(el => el.classList.remove('active'));
            card.classList.add('active');
            loadDetailedFiche(item.siret).catch(console.error);
        });

        resultsList.appendChild(card);
    });
}


// ═══════════════════════════════════════════════════════════════════════
// FICHE DÉTAILLÉE (Golden Record)
// GET /siret/{siret}
// Réponse : { siret, rna, name, status, nature,
//             address: { number, street, postal_code, city,
//                        is_ban_validated, latitude, longitude } }
// ═══════════════════════════════════════════════════════════════════════

async function loadDetailedFiche(siret) {
    if (!siret) return;
    console.log(`Chargement fiche : ${siret}`);

    // Afficher card, masquer placeholder
    document.getElementById('detail-card').classList.remove('d-none');
    document.getElementById('detail-placeholder').classList.add('d-none');
    document.getElementById('detail-title').textContent = 'Chargement…';

    let data;
    try {
        data = await apiCall(API_ENDPOINTS.SIRET(siret));
    } catch (error) {
        // Mode démo
        console.warn('API /siret inaccessible:', error.message);
        data = getMockFiche(siret);
        if (!data) {
            document.getElementById('detail-title').textContent = 'Établissement introuvable';
            showAlert('danger', 'Erreur 404', `Aucune fiche trouvée pour le SIRET ${siret}.`);
            return;
        }
        showAlert('info', 'Mode Démo', 'API hors ligne — données de démonstration.');
    }

    if (data) renderDetailedFiche(data);
}

/**
 * Remplit tous les champs de la fiche.
 */
function renderDetailedFiche(data) {
    const address = data.address || {};

    // ── Header ──────────────────────────────────────────────────────────
    document.getElementById('detail-title').textContent = data.name || '—';
    document.getElementById('detail-enseigne').textContent = '';

    // Badge statut
    const statusBadge = document.getElementById('detail-status-badge');
    if (data.status === 'open') {
        statusBadge.textContent = 'ACTIF';
        statusBadge.className   = 'badge bg-white text-success';
    } else if (data.status === 'closed') {
        statusBadge.textContent = 'FERMÉ';
        statusBadge.className   = 'badge bg-white text-secondary';
    } else {
        statusBadge.textContent = data.status || '—';
        statusBadge.className   = 'badge bg-white text-warning';
    }

    // ── Badge ASSOCIATION ────────────────────────────────────────────────
    const assoBadge = document.getElementById('detail-asso-badge');
    if (data.rna) {
        assoBadge.classList.remove('d-none');
    } else {
        assoBadge.classList.add('d-none');
    }

    // ── Bloc RNA (si association) ────────────────────────────────────────
    const rnaBlock = document.getElementById('detail-rna-block');
    if (data.rna) {
        rnaBlock.classList.remove('d-none');
        document.getElementById('detail-rna-id').textContent = data.rna;

        // Nature / date publication JO
        const dateEl = document.getElementById('detail-rna-date');
        if (data.date_publication_jo) {
            dateEl.textContent = `Publication JO : ${data.date_publication_jo}`;
        } else if (data.nature) {
            dateEl.textContent = `Nature : ${data.nature}`;
        } else {
            dateEl.textContent = '';
        }
    } else {
        rnaBlock.classList.add('d-none');
    }

    // ── Informations légales ─────────────────────────────────────────────
    document.getElementById('detail-siret').textContent = data.siret || '—';

    // categorie_entreprise non exposé par l'API → toujours —
    document.getElementById('detail-categorie').textContent = '—';

    document.getElementById('detail-status-text').innerHTML = data.status === 'open'
        ? '<span class="text-success"><i class="fa-solid fa-circle-check me-1"></i>Actif</span>'
        : '<span class="text-secondary"><i class="fa-solid fa-circle-xmark me-1"></i>Fermé</span>';

    // Enseigne non exposée par l'API
    document.getElementById('detail-enseigne-full').textContent = '—';

    // ── Localisation ─────────────────────────────────────────────────────
    // address.street est déjà concaténé (type_voie + libelle_voie) par le backend
    document.getElementById('detail-address').textContent = [address.number, address.street].filter(Boolean).join(' ') || '—';
    document.getElementById('detail-postal').textContent  = address.postal_code || '—';
    document.getElementById('detail-city').textContent    = address.city        || '—';

    const banEl = document.getElementById('detail-ban-valid');
    if (address.is_ban_validated === true) {
        banEl.innerHTML = '<span class="text-success"><i class="fa-solid fa-circle-check me-1"></i>Validé BAN</span>';
    } else {
        banEl.innerHTML = '<span class="text-muted"><i class="fa-solid fa-circle-xmark me-1"></i>Non validé</span>';
    }

    // ── Carte Leaflet ─────────────────────────────────────────────────────
    if (address.latitude && address.longitude) {
        updateMap(address.latitude, address.longitude, data.name || 'Établissement');
    } else {
        if (!leafletMap) initMap();
        leafletMap.setView([46.603354, 1.888334], 5);
        const coordsDiv = document.getElementById('map-coords');
        if (coordsDiv) {
            coordsDiv.innerHTML = '<i class="fa-solid fa-location-dot me-1 text-muted"></i>Coordonnées GPS non disponibles';
        }
    }

    // ── Widget Stats (pré-rempli avec le CP) ─────────────────────────────
    if (address.postal_code) {
        const cpInput = document.getElementById('stats-cp-input');
        if (cpInput) cpInput.value = address.postal_code;
        document.getElementById('stats-widget').classList.remove('d-none');
        loadStats(address.postal_code).catch(console.error);
    }
}


// ═══════════════════════════════════════════════════════════════════════
// CARTE LEAFLET
// ═══════════════════════════════════════════════════════════════════════

function initMap() {
    if (leafletMap) return;

    leafletMap = L.map('map', {
        center:             [46.603354, 1.888334],
        zoom:               5,
        zoomControl:        true,
        attributionControl: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png', {
        maxZoom:     19,
        attribution: '&copy; OpenStreetMap France',
    }).addTo(leafletMap);

    console.log('Carte Leaflet initialisée');
}

function updateMap(lat, lon, label) {
    if (!leafletMap) initMap();

    try { leafletMap.invalidateSize(); } catch (e) { /* ignore */ }

    if (!lat || !lon || isNaN(parseFloat(lat)) || isNaN(parseFloat(lon))) {
        console.warn('Coordonnées invalides:', lat, lon);
        return;
    }

    // Supprimer l'ancien marqueur
    if (leafletMarker) leafletMap.removeLayer(leafletMarker);

    const defaultIcon = L.icon({
        iconUrl:     'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
        shadowUrl:   'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
        iconSize:    [25, 41],
        iconAnchor:  [12, 41],
        popupAnchor: [1, -34],
        shadowSize:  [41, 41],
    });

    leafletMarker = L.marker([lat, lon], { icon: defaultIcon })
        .addTo(leafletMap)
        .bindPopup(`
            <div style="text-align:center; min-width:160px;">
                <strong>${escapeHtml(label)}</strong><br/>
                <small>${parseFloat(lat).toFixed(5)}, ${parseFloat(lon).toFixed(5)}</small>
            </div>
        `);

    try {
        leafletMap.flyTo([lat, lon], 16, { duration: 1.5, easeLinearity: 0.25 });
    } catch (e) {
        leafletMap.setView([lat, lon], 16);
    }

    setTimeout(() => { if (leafletMarker) leafletMarker.openPopup(); }, 1600);

    const coordsDiv = document.getElementById('map-coords');
    if (coordsDiv) {
        coordsDiv.innerHTML = `
            <i class="fa-solid fa-location-dot me-1 text-primary"></i>
            Lat: <strong>${parseFloat(lat).toFixed(5)}</strong>
            &nbsp;·&nbsp;
            Lon: <strong>${parseFloat(lon).toFixed(5)}</strong>
        `;
    }
}


// ═══════════════════════════════════════════════════════════════════════
// STATISTIQUES
// GET /stats/{cp}
// Réponse : { zone, total_entites,
//             repartition: { entreprises_pures, associations, etablissements_fermes },
//             top_naf: { code, libelle, count } }
// ═══════════════════════════════════════════════════════════════════════

async function loadStats(cpOverride) {
    const cpInput = document.getElementById('stats-cp-input');
    const cpVal   = cpOverride || (cpInput ? cpInput.value.trim() : '');

    if (!/^\d{5}$/.test(cpVal)) {
        if (!cpOverride && cpVal.length > 0) {
            showAlert('warning', 'Code postal invalide', 'Saisissez exactement 5 chiffres (ex: 75014).');
        }
        return;
    }

    document.getElementById('stats-widget').classList.remove('d-none');

    try {
        const data = await apiCall(API_ENDPOINTS.STATS(cpVal));
        renderStats(data);
    } catch (error) {
        console.warn('API /stats inaccessible, mode DÉMO:', error.message);
        renderStats(getMockStats(cpVal));
    }
}

/**
 * Affiche les statistiques.
 */
function renderStats(data) {
    const statsContent = document.getElementById('stats-content');
    if (statsContent) statsContent.classList.remove('d-none');

    const rep          = data.repartition     || {};
    const entreprises  = rep.entreprises_pures     || 0;
    const associations = rep.associations          || 0;
    const fermes       = rep.etablissements_fermes || 0;
    const total        = data.total_entites        || (entreprises + associations) || 1;

    const pctCo  = Math.min(Math.round((entreprises  / total) * 100), 100);
    const pctAs  = Math.min(Math.round((associations  / total) * 100), 100);
    const pctFe  = Math.min(Math.round((fermes        / total) * 100), 100);

    updateStatBar('bar-companies', 'val-companies', pctCo,  entreprises);
    updateStatBar('bar-asso',      'val-asso',      pctAs,  associations);
    updateStatBar('bar-closed',    'val-closed',    pctFe,  fermes);

    // ── Top NAF ──────────────────────────────────────────────────────────
    const topNaf    = data.top_naf || {};
    const nafCodeEl = document.getElementById('top-naf-code');
    const nafCountEl = document.getElementById('top-naf-count');

    if (nafCodeEl) {
        if (topNaf.code) {
            nafCodeEl.textContent = topNaf.libelle
                ? `${topNaf.code} — ${topNaf.libelle}`
                : topNaf.code;
        } else {
            nafCodeEl.textContent = 'Non disponible';
        }
    }
    if (nafCountEl) {
        nafCountEl.textContent = topNaf.count
            ? `${formatNumber(topNaf.count)} établissements dans cette activité`
            : '';
    }
}

function updateStatBar(barId, valId, percent, value) {
    const bar = document.getElementById(barId);
    const val = document.getElementById(valId);
    if (bar) {
        bar.style.width = `${percent}%`;
        bar.setAttribute('aria-valuenow', String(percent));
    }
    if (val) val.textContent = formatNumber(value);
}


// ═══════════════════════════════════════════════════════════════════════
// DONNÉES MOCK — Format exactement aligné sur le format réel de l'API
// ═══════════════════════════════════════════════════════════════════════

/**
 * Mock /search — utilise "address_city" (clé réelle de l'API, Exemple 4)
 */
function getMockSearchData(query) {
    return {
        count: 3,
        query: query,
        filter_dept: null,
        results: [
            {
                siret:          '77567227200020',
                name:           'CROIX ROUGE FRANCAISE',
                address_city:   'PARIS',
                is_association: true
            },
            {
                siret:          '44312012000015',
                name:           'LA PETITE BOULANGERIE',
                address_city:   'LYON',
                is_association: false
            },
            {
                siret:          '13002526500013',
                name:           'DIRECTION INTERMINISTERIELLE DU NUMERIQUE',
                address_city:   'PARIS',
                is_association: false
            }
        ]
    };
}

/**
 * Mock /siret/{siret} — aligné sur le format court réel de l'API (Exemples 1 & 2)
 * { siret, rna, name, status, nature, address: { number, street, postal_code, city,
 *   is_ban_validated, latitude, longitude } }
 */
function getMockFiche(siret) {
    const fiches = {
        // ─── Croix Rouge Française — Gold Case ──────────────────────────
        '77567227200020': {
            siret:   '77567227200020',
            rna:     'W751000060',
            name:    'CROIX ROUGE FRANCAISE',
            status:  'open',
            nature:  'ASSOCIATION',
            address: {
                number:           '98',
                street:           'RUE DIDOT',
                postal_code:      '75014',
                city:             'PARIS',
                is_ban_validated: true,
                latitude:         48.8296,
                longitude:        2.3235
            }
        },
        // ─── DINUM — Gold Case ──────────────────────────────────────────
        '13002526500013': {
            siret:   '13002526500013',
            rna:     null,
            name:    'DIRECTION INTERMINISTERIELLE DU NUMERIQUE',
            status:  'open',
            nature:  null,
            address: {
                number:           '20',
                street:           'AV DE SEGUR',
                postal_code:      '75007',
                city:             'PARIS',
                is_ban_validated: true,
                latitude:         48.850699,
                longitude:        2.308628
            }
        },
        // ─── La Petite Boulangerie ────────────────────────────────────
        '44312012000015': {
            siret:   '44312012000015',
            rna:     null,
            name:    'LA PETITE BOULANGERIE',
            status:  'open',
            nature:  null,
            address: {
                number:           '12',
                street:           'RUE DE LA REPUBLIQUE',
                postal_code:      '69002',
                city:             'LYON',
                is_ban_validated: true,
                latitude:         45.7640,
                longitude:        4.8357
            }
        }
    };

    return fiches[siret] || null;
}

/**
 * Mock /stats/{cp} — format réel de l'API
 */
function getMockStats(cp) {
    const seed  = parseInt(cp.replace(/\D/g, '')) || 75000;
    const total = (seed % 1000) * 15 + 500;
    return {
        zone:           cp,
        total_entites:  total,
        repartition: {
            entreprises_pures:     Math.floor(total * 0.78),
            associations:          Math.floor(total * 0.12),
            etablissements_fermes: Math.floor(total * 0.22)
        },
        top_naf: {
            code:    '56.10A',
            libelle: null,
            count:   Math.floor(total * 0.08)
        }
    };
}


// ═══════════════════════════════════════════════════════════════════════
// UTILITAIRES
// ═══════════════════════════════════════════════════════════════════════

/**
 * Formate un nombre en notation fr-FR (séparateur de milliers)
 */
function formatNumber(n) {
    if (n === null || n === undefined || n === '') return '—';
    return Number(n).toLocaleString('fr-FR');
}

/**
 * Protège contre les injections HTML dans les textes injectés via innerHTML
 */
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Affiche une alerte Bootstrap flottante en haut de page (auto-dismiss 5s)
 */
function showAlert(type, title, message) {
    const existing = document.querySelectorAll('.alert-floating');
    existing.forEach(a => a.remove());

    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show alert-floating position-fixed top-0 start-50 translate-middle-x mt-3`;
    alert.style.cssText = 'z-index:9999; min-width:360px; max-width:90vw; box-shadow: 0 4px 20px rgba(0,0,0,0.15);';
    alert.innerHTML = `
        <strong>${escapeHtml(title)}</strong><br>
        <small>${escapeHtml(message)}</small>
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Fermer"></button>
    `;
    document.body.appendChild(alert);
    setTimeout(() => { if (alert.parentNode) alert.remove(); }, 5000);
}

/**
 * Remplit la barre de recherche de la home ET lance la recherche.
 * Appelé par les boutons "Essayez : Croix Rouge (75)"
 */
function fillSearchHome(query, dept) {
    const inputHome = document.getElementById('search-input-home');
    const deptHome  = document.getElementById('dept-input-home');
    if (inputHome) inputHome.value = query;
    if (deptHome)  deptHome.value  = dept;
    handleSearch(query, dept).catch(console.error);
}


// ═══════════════════════════════════════════════════════════════════════
// DARK MODE
// ═══════════════════════════════════════════════════════════════════════

function initTheme() {
    let theme = localStorage.getItem('theme');
    if (!theme) {
        theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    applyTheme(theme);

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        if (!localStorage.getItem('theme')) {
            applyTheme(e.matches ? 'dark' : 'light');
        }
    });
}

function toggleTheme() {
    const current  = document.body.getAttribute('data-theme') || 'light';
    const newTheme = current === 'light' ? 'dark' : 'light';
    applyTheme(newTheme);
    localStorage.setItem('theme', newTheme);
}

function applyTheme(theme) {
    document.body.setAttribute('data-theme', theme);
    if (theme === 'dark') {
        document.body.classList.remove('bg-white');
        document.body.classList.add('bg-dark');
    } else {
        document.body.classList.remove('bg-dark');
        document.body.classList.add('bg-white');
    }
    updateThemeIcon(theme);
}

function updateThemeIcon(theme) {
    const icon = document.querySelector('#theme-toggle i');
    if (!icon) return;
    icon.className = theme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
}


// ═══════════════════════════════════════════════════════════════════════
// FIN
// ═══════════════════════════════════════════════════════════════════════

console.log('app.js chargé — aligné format API (siret/rna/name/address/*)');
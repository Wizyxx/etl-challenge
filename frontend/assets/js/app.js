/* global L, API_ENDPOINTS, apiCall */

/**
 * ══════════════════════════════════════════════════════════════════════
 * APP.JS — Logique Principale du Frontend
 * 5 Days Challenge — Référentiel Unifié SIRENE × RNA × BAN
 * ══════════════════════════════════════════════════════════════════════
 */

let leafletMap    = null;
let leafletMarker = null;
let currentResults = [];


// ═══════════════════════════════════════════════════════════════════════
// INITIALISATION
// ═══════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    console.log('App démarrée — Référentiel Unifié v5 (Production)');
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
            throw new Error('Réponse inattendue');
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
    // ── Page Home — recherche ──
    const btnHome   = document.getElementById('btn-search-home');
    const inputHome = document.getElementById('search-input-home');
    const deptHome  = document.getElementById('dept-input-home');

    const triggerHome = () => {
        handleSearch(inputHome.value.trim(), deptHome.value.trim()).catch(console.error);
    };

    if (btnHome)  btnHome.addEventListener('click', triggerHome);
    [inputHome, deptHome].forEach(el => {
        if (el) el.addEventListener('keydown', e => { if (e.key === 'Enter') triggerHome(); });
    });

    // ── Page Home — stats ──
    const cpInputHome = document.getElementById('stats-cp-input-home');
    if (cpInputHome) {
        cpInputHome.addEventListener('keydown', e => {
            if (e.key === 'Enter') loadStatsHome().catch(console.error);
        });
    }

    // ── Page Résultats — re-recherche ──
    const btnResults   = document.getElementById('btn-search-results');
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

    // ── Page Résultats — stats ──
    const cpInput = document.getElementById('stats-cp-input');
    if (cpInput) {
        cpInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') loadStats().catch(console.error);
        });
    }

    // ── Theme toggle ──
    const toggleBtn = document.getElementById('theme-toggle');
    if (toggleBtn) toggleBtn.addEventListener('click', toggleTheme);
}


// ═══════════════════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════════════════

function showHome() {
    document.getElementById('page-home').classList.remove('d-none');
    document.getElementById('page-results').classList.add('d-none');

    // Vider les champs home
    const homeInput = document.getElementById('search-input-home');
    const homeDept  = document.getElementById('dept-input-home');
    if (homeInput) homeInput.value = '';
    if (homeDept)  homeDept.value  = '';

    setTimeout(() => { if (homeInput) homeInput.focus(); }, 100);
    resetResultsState();
    resetMap();
}

function showResults() {
    document.getElementById('page-home').classList.add('d-none');
    document.getElementById('page-results').classList.remove('d-none');
}

function resetResultsState() {
    currentResults = [];

    const countEl = document.getElementById('results-count');
    if (countEl) countEl.textContent = 'Résultats de recherche';

    const resultsList = document.getElementById('results-list');
    if (resultsList) {
        resultsList.innerHTML = `
            <div class="list-group-item text-center text-muted py-5">
                <i class="fa-regular fa-folder-open fa-3x mb-3 opacity-50"></i><br>
                Lancez une recherche pour voir les résultats.
            </div>
        `;
    }

    const spinner = document.getElementById('loading-spinner');
    if (spinner) spinner.classList.add('d-none');

    document.getElementById('detail-card').classList.add('d-none');
    document.getElementById('detail-placeholder').classList.remove('d-none');

    const statsWidget = document.getElementById('stats-widget');
    if (statsWidget) statsWidget.classList.add('d-none');

    const inputResults = document.getElementById('search-input-results');
    const deptResults  = document.getElementById('dept-input-results');
    if (inputResults) inputResults.value = '';
    if (deptResults)  deptResults.value  = '';

    resetDetailCard();
}

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

    const statusBadge = document.getElementById('detail-status-badge');
    if (statusBadge) { statusBadge.textContent = ''; statusBadge.className = 'badge'; }

    document.getElementById('detail-asso-badge')?.classList.add('d-none');
    document.getElementById('detail-rna-block')?.classList.add('d-none');

    ['bar-companies', 'bar-asso', 'bar-closed'].forEach(id => {
        const bar = document.getElementById(id);
        if (bar) { bar.style.width = '0%'; bar.setAttribute('aria-valuenow', '0'); }
    });

    const statsContent = document.getElementById('stats-content');
    if (statsContent) statsContent.classList.add('d-none');
}

function resetMap() {
    if (leafletMap) {
        if (leafletMarker) {
            leafletMap.removeLayer(leafletMarker);
            leafletMarker = null;
        }
        try { leafletMap.setView([46.603354, 1.888334], 5); } catch (e) { /* ignore */ }
    }

    const coordsDiv = document.getElementById('map-coords');
    if (coordsDiv) {
        coordsDiv.innerHTML = '<i class="fa-solid fa-location-dot me-1"></i>Coordonnées : —';
    }
}


// ═══════════════════════════════════════════════════════════════════════
// RECHERCHE PRINCIPALE
// ═══════════════════════════════════════════════════════════════════════

async function handleSearch(query, dept) {
    const q = (query || '').trim();
    const d = (dept  || '').trim();

    if (q.length < 2) {
        showAlert('warning', 'Recherche trop courte', 'Saisissez au moins 2 caractères.');
        return;
    }

    // ── CAS 1 : SIRET exact (14 chiffres) → fiche directe ──────────────
    if (/^\d{14}$/.test(q)) {
        showResults();
        const ir = document.getElementById('search-input-results');
        const dr = document.getElementById('dept-input-results');
        if (ir) ir.value = q;
        if (dr) dr.value = d;
        resetResultsState();
        document.getElementById('detail-placeholder').classList.add('d-none');
        document.getElementById('detail-card').classList.remove('d-none');
        document.getElementById('detail-title').textContent = 'Chargement…';
        await loadDetailedFiche(q);
        return;
    }

    // ── CAS 2 : Format numérique invalide ──────────────────────────────
    if (/^\d+$/.test(q) && q.length !== 14) {
        showAlert('warning', 'Format invalide', 'Un SIRET doit contenir exactement 14 chiffres.');
        return;
    }

    // ── CAS 3 : Recherche textuelle → /search?q=...&dept=... ───────────
    showResults();

    const loader      = document.getElementById('loading-spinner');
    const resultsList = document.getElementById('results-list');
    loader.classList.remove('d-none');
    resultsList.innerHTML = '';

    const ir = document.getElementById('search-input-results');
    const dr = document.getElementById('dept-input-results');
    if (ir) ir.value = q;
    if (dr) dr.value = d;

    document.getElementById('detail-card').classList.add('d-none');
    document.getElementById('detail-placeholder').classList.remove('d-none');
    document.getElementById('stats-widget').classList.add('d-none');

    try {
        const params = new URLSearchParams({ q });
        if (d) {
            const deptVal = d.length === 5 ? d.substring(0, 2) : d;
            params.append('dept', deptVal);
        }

        const data = await apiCall(`${API_ENDPOINTS.SEARCH}?${params.toString()}`);
        currentResults = data.results || [];
        renderResults(data);

    } catch (error) {
        console.error('Erreur lors de la recherche:', error);
        loader.classList.add('d-none');
        resultsList.innerHTML = `
            <div class="list-group-item text-center text-danger py-5">
                <i class="fa-solid fa-triangle-exclamation fa-3x mb-3 opacity-75"></i><br>
                <strong>Erreur de recherche</strong><br>
                <small>${escapeHtml(error.message)}</small>
            </div>
        `;
        showAlert('danger', 'Erreur API', error.message);
    }
}


// ═══════════════════════════════════════════════════════════════════════
// RENDU LISTE RÉSULTATS
// ═══════════════════════════════════════════════════════════════════════

function renderResults(data) {
    const loader       = document.getElementById('loading-spinner');
    const resultsList  = document.getElementById('results-list');
    const resultsCount = document.getElementById('results-count');

    loader.classList.add('d-none');

    const count   = data.count   || 0;
    const results = data.results || [];

    if (resultsCount) {
        resultsCount.innerHTML = `
            <strong>${count}</strong> résultat${count > 1 ? 's' : ''}
            ${data.query ? `pour « <em>${escapeHtml(data.query)}</em> »` : ''}
            ${data.filter_dept ? `— Dép. <strong>${escapeHtml(data.filter_dept)}</strong>` : ''}
        `;
    }

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
        const isAsso    = item.is_association === true;
        const cityLabel = item.address_city || item.city || '—';

        const iconClass = isAsso ? 'fa-landmark text-danger' : 'fa-building text-primary';
        const badgeHtml = isAsso
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
            document.querySelectorAll('.result-item').forEach(el => el.classList.remove('active'));
            card.classList.add('active');
            loadDetailedFiche(item.siret).catch(console.error);
        });

        resultsList.appendChild(card);
    });
}


// ═══════════════════════════════════════════════════════════════════════
// FICHE DÉTAILLÉE — GET /siret/{siret}
// ═══════════════════════════════════════════════════════════════════════

async function loadDetailedFiche(siret) {
    if (!siret) return;

    document.getElementById('detail-card').classList.remove('d-none');
    document.getElementById('detail-placeholder').classList.add('d-none');
    document.getElementById('detail-title').textContent = 'Chargement…';

    try {
        const data = await apiCall(API_ENDPOINTS.SIRET(siret));
        renderDetailedFiche(data);
    } catch (error) {
        console.error('Erreur lors de la récupération du SIRET:', error);
        document.getElementById('detail-title').textContent = 'Établissement introuvable';
        showAlert('danger', 'Erreur API', error.message);
    }
}

function renderDetailedFiche(data) {
    const address = data.address || {};

    // ── Header ──────────────────────────────────────────────────────────
    document.getElementById('detail-title').textContent = data.name || '—';
    document.getElementById('detail-enseigne').textContent = '';

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

    const assoBadge = document.getElementById('detail-asso-badge');
    if (data.rna) {
        assoBadge.classList.remove('d-none');
    } else {
        assoBadge.classList.add('d-none');
    }

    // ── Bloc RNA ─────────────────────────────────────────────────────────
    const rnaBlock = document.getElementById('detail-rna-block');
    if (data.rna) {
        rnaBlock.classList.remove('d-none');
        document.getElementById('detail-rna-id').textContent = data.rna;

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
    document.getElementById('detail-categorie').textContent = data.categorie_entreprise || '—';

    document.getElementById('detail-status-text').innerHTML = data.status === 'open'
        ? '<span class="text-success"><i class="fa-solid fa-circle-check me-1"></i>Actif</span>'
        : '<span class="text-secondary"><i class="fa-solid fa-circle-xmark me-1"></i>Fermé</span>';

    document.getElementById('detail-enseigne-full').textContent = data.enseigne || '—';

    // ── Localisation ──────────────────────────────────────────────────────
    document.getElementById('detail-address').textContent = [address.number, address.street].filter(Boolean).join(' ') || '—';
    document.getElementById('detail-postal').textContent  = address.postal_code || '—';
    document.getElementById('detail-city').textContent    = address.city        || '—';

    const banEl = document.getElementById('detail-ban-valid');
    if (address.is_ban_validated === true) {
        banEl.innerHTML = '<span class="text-success"><i class="fa-solid fa-circle-check me-1"></i>Validé BAN</span>';
    } else {
        banEl.innerHTML = '<span class="text-muted"><i class="fa-solid fa-circle-xmark me-1"></i>Non validé</span>';
    }

    // ── Carte Leaflet ──────────────────────────────────────────────────────
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

    // ── Widget Stats ───────────────────────────────────────────────────────
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
}

function updateMap(lat, lon, label) {
    if (!leafletMap) initMap();

    try { leafletMap.invalidateSize(); } catch (e) { /* ignore */ }

    if (!lat || !lon || isNaN(parseFloat(lat)) || isNaN(parseFloat(lon))) return;

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
// STATISTIQUES — GET /stats/{cp}
// ═══════════════════════════════════════════════════════════════════════

async function loadStats(cpOverride) {
    const cpInput = document.getElementById('stats-cp-input');
    const cpVal   = cpOverride || (cpInput ? cpInput.value.trim() : '');

    if (!/^\d{5}$/.test(cpVal)) return;

    document.getElementById('stats-widget').classList.remove('d-none');

    try {
        const data = await apiCall(API_ENDPOINTS.STATS(cpVal));
        renderStats(data, 'results');
    } catch (error) {
        console.error('Erreur API /stats :', error);
        document.getElementById('stats-widget').classList.add('d-none');
    }
}

async function loadStatsHome(cpOverride) {
    const cpInput = document.getElementById('stats-cp-input-home');
    const cpVal   = cpOverride || (cpInput ? cpInput.value.trim() : '');

    if (!/^\d{5}$/.test(cpVal)) return;

    try {
        const data = await apiCall(API_ENDPOINTS.STATS(cpVal));
        renderStats(data, 'home');
    } catch (error) {
        console.error('Erreur API /stats home :', error);
    }
}

function quickStats(cp) {
    const cpInput = document.getElementById('stats-cp-input-home');
    if (cpInput) cpInput.value = cp;
    loadStatsHome(cp).catch(console.error);
}

function renderStats(data, zone) {
    const suffix = zone === 'home' ? '-home' : '';

    const statsContent = document.getElementById(`stats-content${suffix}`);
    if (statsContent) statsContent.classList.remove('d-none');

    const rep         = data.repartition     || {};
    const entreprises = rep.entreprises_pures     || 0;
    const associations= rep.associations          || 0;
    const fermes      = rep.etablissements_fermes || 0;
    const total       = data.total_entites        || (entreprises + associations) || 1;

    const pctCo = Math.min(Math.round((entreprises  / total) * 100), 100);
    const pctAs = Math.min(Math.round((associations  / total) * 100), 100);
    const pctFe = Math.min(Math.round((fermes        / total) * 100), 100);

    updateStatBar(`bar-companies${suffix}`, `val-companies${suffix}`, pctCo,  entreprises);
    updateStatBar(`bar-asso${suffix}`,      `val-asso${suffix}`,      pctAs,  associations);
    updateStatBar(`bar-closed${suffix}`,    `val-closed${suffix}`,    pctFe,  fermes);

    const topNaf     = data.top_naf || {};
    const nafCodeEl  = document.getElementById(`top-naf-code${suffix}`);
    const nafCountEl = document.getElementById(`top-naf-count${suffix}`);

    if (nafCodeEl) {
        nafCodeEl.textContent = topNaf.code
            ? (topNaf.libelle ? `${topNaf.code} — ${topNaf.libelle}` : topNaf.code)
            : 'Non disponible';
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
// UTILITAIRES
// ═══════════════════════════════════════════════════════════════════════

function formatNumber(n) {
    if (n === null || n === undefined || n === '') return '—';
    return Number(n).toLocaleString('fr-FR');
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function showAlert(type, title, message) {
    document.querySelectorAll('.alert-floating').forEach(a => a.remove());

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
        if (!localStorage.getItem('theme')) applyTheme(e.matches ? 'dark' : 'light');
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

console.log('app.js v5 — 100% Production sans fausses données');
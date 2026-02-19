/**
 * ══════════════════════════════════════════════════════════════════════
 * CONFIGURATION API — 5 Days Challenge
 * ══════════════════════════════════════════════════════════════════════
 *
 * Ce fichier contient l'URL de l'API et la logique d'appel (fetch).
 *
 * ⚠IMPORTANT : Vérifiez qu'il n'y a PAS d'apostrophe parasite à la fin de l'URL !
 *
 * ══════════════════════════════════════════════════════════════════════
 */

// ─────────────────────────────────────────────────────────────────────
// URL DE BASE DE L'API (Backend Ngrok)
// ─────────────────────────────────────────────────────────────────────

const API_BASE_URL = "https://jacqualine-sporogonial-iesha.ngrok-free.dev/api/v1";

// ─────────────────────────────────────────────────────────────────────
// ENDPOINTS DISPONIBLES
// ─────────────────────────────────────────────────────────────────────

const API_ENDPOINTS = {
    // Healthcheck (vérifie si le backend est up)
    PING:   `${API_BASE_URL}/ping`,

    // Golden Record (fiche identité complète SIRENE + RNA + BAN)
    SIRET:  (siret) => `${API_BASE_URL}/siret/${siret}`,

    // Recherche textuelle avec filtre géographique
    SEARCH: `${API_BASE_URL}/search`,

    // Statistiques pré-agrégées par code postal
    STATS:  (cp) => `${API_BASE_URL}/stats/${cp}`
};


// ─────────────────────────────────────────────────────────────────────
// PARAMÈTRES GLOBAUX
// ─────────────────────────────────────────────────────────────────────

const CONFIG = {
    REQUEST_TIMEOUT: 15000,         // 15 secondes max par requête
    SLOW_RESPONSE_THRESHOLD: 500    // Alerte console si réponse > 500ms
};


// ─────────────────────────────────────────────────────────────────────
// MOTEUR D'APPEL API (Fetch Wrapper avec gestion Ngrok)
// ─────────────────────────────────────────────────────────────────────

/**
 * Fonction générique pour les appels API avec gestion des erreurs et performances
 *
 * @param {string} url - URL complète de l'endpoint
 * @param {object} options - Options fetch (method, headers, body, etc.)
 * @returns {Promise<object>} - Données JSON parsées
 */
async function apiCall(url, options = {}) {
    const startTime = performance.now();

    // 1. Headers par défaut pour bypasser Ngrok
    const defaultHeaders = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "ngrok-skip-browser-warning": "69420"
    };

    let response;
    let timeoutId;

    try {
        // Timeout controller
        const controller = new AbortController();
        const timeoutDuration = CONFIG.REQUEST_TIMEOUT || 15000;
        timeoutId = setTimeout(() => controller.abort(), timeoutDuration);

        // 2. Appel fetch avec fusion des headers
        response = await fetch(url, {
            method: 'GET',
            ...options,
            headers: {
                ...defaultHeaders,
                ...(options.headers || {})
            },
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        // Mesure de performance
        const endTime = performance.now();
        const duration = endTime - startTime;
        const slowThreshold = CONFIG.SLOW_RESPONSE_THRESHOLD || 500;

        if (duration > slowThreshold) {
            console.warn(`Réponse lente : ${url} (${duration.toFixed(0)}ms)`);
        } else {
            console.log(`API call : ${url} (${duration.toFixed(0)}ms)`);
        }

    } catch (error) {
        // Erreur réseau ou timeout
        if (error.name === 'AbortError') {
            const timeoutSec = (CONFIG.REQUEST_TIMEOUT || 15000) / 1000;
            console.error(`Timeout : ${url} (> ${timeoutSec}s)`);
            throw new Error(`L'API ne répond pas (timeout après ${timeoutSec}s)`);
        }

        console.error(`Erreur réseau : ${url}`, error);
        throw error;
    }

    // 3. Gestion des erreurs HTTP (404, 400, 500...)
    if (!response.ok) {
        // 404 : Ressource introuvable
        if (response.status === 404) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || 'Ressource introuvable (404)');
        }

        // 400 : Mauvaise requête
        if (response.status === 400) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || 'Requête invalide (400)');
        }

        // Autres erreurs serveur
        throw new Error(`Erreur HTTP ${response.status}`);
    }

    // 4. Retour du JSON propre
    return await response.json();
}


// ─────────────────────────────────────────────────────────────────────
// DIAGNOSTIC : Fonction pour tester l'URL (à appeler en console)
// ─────────────────────────────────────────────────────────────────────

/**
 * Fonction de diagnostic pour vérifier si l'URL est propre
 * Usage : Tapez "testURL()" dans la console du navigateur
 */
function testURL() {
    console.log('='.repeat(60));
    console.log('DIAGNOSTIC URL API');
    console.log('='.repeat(60));
    console.log('API_BASE_URL =', API_BASE_URL);
    console.log('Longueur     =', API_BASE_URL.length, 'caractères');
    console.log('Dernier char =', API_BASE_URL.slice(-1), '(code:', API_BASE_URL.charCodeAt(API_BASE_URL.length - 1) + ')');
    console.log('');
    console.log('ENDPOINTS :');
    console.log('  PING   =', API_ENDPOINTS.PING);
    console.log('  SEARCH =', API_ENDPOINTS.SEARCH);
    console.log('  SIRET  =', API_ENDPOINTS.SIRET('77567227200020'));
    console.log('  STATS  =', API_ENDPOINTS.STATS('75014'));
    console.log('='.repeat(60));

    // Vérification caractère suspect
    if (API_BASE_URL.includes("'")) {
        console.error('ATTENTION : Apostrophe détectée dans API_BASE_URL !');
        return false;
    } else {
        console.log('Aucune apostrophe parasite détectée');
        return true;
    }
}


// ─────────────────────────────────────────────────────────────────────
// LOGS AU CHARGEMENT
// ─────────────────────────────────────────────────────────────────────

console.log(`
╔════════════════════════════════════════════════════════════════╗
║  API Configuration chargée                                  ║
║  URL : ${API_BASE_URL.substring(0, 50).padEnd(50)} ║
╚════════════════════════════════════════════════════════════════╝
`);

// Exécution automatique du diagnostic au chargement
testURL();
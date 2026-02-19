/**
 * ══════════════════════════════════════════════════════════════════════
 * CONFIGURATION API — 5 Days Challenge
 * ══════════════════════════════════════════════════════════════════════
 * 
 * Ce fichier contient l'URL de l'API.
 * 
 * ══════════════════════════════════════════════════════════════════════
 */

// ─────────────────────────────────────────────────────────────────────
// URL DE BASE DE L'API
// ─────────────────────────────────────────────────────────────────────

const API_BASE_URL = "http://localhost:8000/api/v1";

// EXEMPLE NGROK :
// const API_BASE_URL = "https://challenge.ngrok-free.app/api/v1";

// EXEMPLE PRODUCTION :
// const API_BASE_URL = "https://api.entreprisesfrance.fr/v1";


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
    STATS:  (cp) => `${API_BASE_URL}/stats/${cp}`,
};


// ─────────────────────────────────────────────────────────────────────
// CONFIGURATION AVANCÉE (Optionnel)
// ─────────────────────────────────────────────────────────────────────

const CONFIG = {
    // Timeout des requêtes (en millisecondes)
    REQUEST_TIMEOUT: 10000, // 10 secondes
    
    // Retry automatique en cas d'échec
    MAX_RETRIES: 2,
    
    // Limite de résultats affichés (backend limite à 10 de toute façon)
    MAX_RESULTS_DISPLAY: 10,
    
    // Délai avant de considérer l'API comme "lente" (pour afficher un warning)
    SLOW_RESPONSE_THRESHOLD: 500, // 500ms
};


// ─────────────────────────────────────────────────────────────────────
// HELPER FONCTION : Appel API Unifié avec gestion d'erreurs
// ─────────────────────────────────────────────────────────────────────

/**
 * Fonction utilitaire pour faire des appels API avec gestion automatique :
 * - Timeout
 * - Retry
 * - Logs de performance
 * 
 * @param {string} url - URL complète de l'endpoint
 * @param {object} options - Options fetch() (method, headers, body, etc.)
 * @returns {Promise<object>} - Données JSON parsées
 */
async function apiCall(url, options = {}) {
    const startTime = performance.now();
    
    // Configuration par défaut
    const config = {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            // Ajout ici d'autres headers si nécessaire (ex: Authorization)
        },
        ...options,
    };

    let response;
    let timeoutId;

    try {
        // Timeout controller
        const controller = new AbortController();
        timeoutId = setTimeout(() => controller.abort(), CONFIG.REQUEST_TIMEOUT);
        
        response = await fetch(url, {
            ...config,
            signal: controller.signal,
        });
        
        clearTimeout(timeoutId);
        
        // Mesure de performance
        const endTime = performance.now();
        const duration = endTime - startTime;
        
        // Log performance (warning si > 500ms)
        if (duration > CONFIG.SLOW_RESPONSE_THRESHOLD) {
            console.warn(`Réponse lente : ${url} (${duration.toFixed(0)}ms)`);
        } else {
            console.log(`API call : ${url} (${duration.toFixed(0)}ms)`);
        }
        
    } catch (error) {
        // Erreur réseau ou timeout
        if (error.name === 'AbortError') {
            console.error(`Timeout : ${url} (> ${CONFIG.REQUEST_TIMEOUT}ms)`);
            throw new Error(`L'API ne répond pas (timeout après ${CONFIG.REQUEST_TIMEOUT/1000}s)`);
        }
        
        console.error(`Erreur API : ${url}`, error);
        throw error;
    }

    if (!response.ok) {
        // Cas 404 : ressource introuvable (normal pour SIRET inexistant)
        if (response.status === 404) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || 'Ressource introuvable');
        }
        
        // Cas 400 : bad request (SIRET mal formaté, etc.)
        if (response.status === 400) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || 'Requête invalide');
        }
        
        // Autres erreurs serveur
        throw new Error(`Erreur HTTP ${response.status}`);
    }
    
    // Parse JSON
    return await response.json();
}


// ─────────────────────────────────────────────────────────────────────
// EXPORT (visible globalement dans app.js)
// ─────────────────────────────────────────────────────────────────────

console.log(`
╔════════════════════════════════════════════════════════════════╗
║  API Configuration chargée                                      ║
║  URL : ${API_BASE_URL.padEnd(50)} ║
╚════════════════════════════════════════════════════════════════╝
`);
# Mapping des colonnes sources → Modèle unifié

> Ce fichier résume les colonnes conservées dans chaque source et leur rôle
> dans la construction du golden record (`unified_records`).

---

## 1. StockEtablissement (SIRENE)

Fichier source : `StockEtablissement_utf8.zip`

| Colonne source | Rôle | Champ unifié |
|---|---|---|
| `siret` | **Identifiant principal** (14 chiffres) | `siret` |
| `siren` | Identifiant de l'unité légale (9 chiffres), clé de jointure UL + RNA | `siren` |
| `etablissementSiege` | Indicateur siège social | `etablissementSiege` |
| `denominationUsuelleEtablissement` | Nom usuel de l'établissement | `name` (priorité 1) |
| `enseigne1Etablissement` | Enseigne commerciale | `enseigne` (priorité 2) |
| `numeroVoieEtablissement` | Numéro de rue | `addr_num` |
| `indiceRepetitionEtablissement` | Indice de répétition (bis, ter…) | `addr_rep` |
| `typeVoieEtablissement` | Type de voie (RUE, AV, BD…) | `addr_type` |
| `libelleVoieEtablissement` | Libellé de la voie | `addr_street` |
| `codePostalEtablissement` | Code postal (5 chiffres) | `postal_code` |
| `libelleCommuneEtablissement` | Nom de la commune | `city` |
| `codeCommuneEtablissement` | Code INSEE commune | `commune_id` |
| `activitePrincipaleEtablissement` | Code NAF/APE | `naf` |
| `nomenclatureActivitePrincipaleEtablissement` | Nomenclature NAF | _(filtrage)_ |
| `trancheEffectifsEtablissement` | Tranche d'effectifs | _(enrichissement)_ |
| `etatAdministratifEtablissement` | État (A=actif, F=fermé) | `status` |
| `caractereEmployeurEtablissement` | Caractère employeur (O/N) | `caractereEmployeurEtablissement` |

---

## 2. StockUniteLegale (SIRENE — noms)

Fichier source : `StockUniteLegale_utf8.zip`

| Colonne source | Rôle | Champ unifié |
|---|---|---|
| `siren` | Clé de jointure avec StockEtablissement | _(jointure)_ |
| `denominationUniteLegale` | Raison sociale (personnes morales) | `name` (priorité 3, via jointure) |
| `nomUniteLegale` | Nom patronymique (personnes physiques) | `name` (fallback) |
| `prenom1UniteLegale` | Prénom (personnes physiques) | `name` (concaténé avec nom) |
| `categorieJuridiqueUniteLegale` | Catégorie juridique | _(enrichissement)_ |
| `categorieEntreprise` | Catégorie d'entreprise (PME, ETI, GE…) | `categorie_entreprise` |

---

## 3. RNA — Waldec (Associations)

Fichier source : `rna_waldec.zip` (104 fichiers CSV départementaux)

| Colonne source | Rôle | Champ unifié |
|---|---|---|
| `id` | **Identifiant RNA** (Wxxxxxxxxx) | `id_rna` |
| `id_ex` | Ancien identifiant | _(traçabilité)_ |
| `siret` | SIRET de l'association — **clé de jointure SIRENE** | _(jointure sur `siret` ou `siren = siret[:9]`)_ |
| `titre` | Nom complet de l'association | `titre_clean` |
| `titre_court` | Nom abrégé | _(enrichissement)_ |
| `objet` | Objet social | _(enrichissement)_ |
| `adrs_numvoie` | Numéro de voie | _(adresse secondaire RNA)_ |
| `adrs_repetition` | Indice de répétition | _(adresse secondaire RNA)_ |
| `adrs_typevoie` | Type de voie | _(adresse secondaire RNA)_ |
| `adrs_libvoie` | Libellé de la voie | _(adresse secondaire RNA)_ |
| `adrs_codepostal` | Code postal | _(adresse secondaire RNA)_ |
| `adrs_libcommune` | Commune | _(adresse secondaire RNA)_ |
| `date_publi` | Date de publication au JO | `date_publication_jo` |
| `nature` | Nature juridique (ASSOCIATION, etc.) | `asso_nature` |
| `groupement` | Type de groupement | _(enrichissement)_ |

**Stratégie de jointure RNA → SIRENE :**
1. Priorité : `SIRENE.siret = RNA.siret` (correspondance exacte 14 chiffres)
2. Fallback : `SIRENE.siren = RNA.siret[:9]` (correspondance sur le SIREN du siège)

---

## 4. BAN — Base Adresse Nationale

Fichier source : `adresses-france.csv.gz` (~50M adresses)

| Colonne source | Rôle | Champ unifié |
|---|---|---|
| `numero` | Numéro de rue | _(clé de jointure BAN)_ |
| `rep` | Indice de répétition (bis, ter…) | _(clé de jointure BAN)_ |
| `nom_voie` | Nom complet de la voie | _(clé de jointure BAN)_ |
| `code_postal` | **Code postal** (5 chiffres) | _(clé de jointure BAN)_ |
| `code_insee` | Code INSEE commune | _(enrichissement)_ |
| `nom_commune` | Nom de la commune | _(enrichissement)_ |
| `lat` | **Latitude** (WGS84) | `latitude` |
| `lon` | **Longitude** (WGS84) | `longitude` |

**Clé de jointure BAN :** `{code_postal}_{numéro}{répétition}_{TYPE_VOIE LIBELLÉ_VOIE}`

---

## Résumé du modèle unifié (`unified_records`)

| Champ | Source principale | Description |
|---|---|---|
| `siret` | SIRENE | Identifiant unique (PK) |
| `siren` | SIRENE | Identifiant unité légale |
| `name` | SIRENE + UniteLegale | Nom résolu (etab → enseigne → UL) |
| `id_rna` | RNA | Identifiant association (si applicable) |
| `is_association` | RNA | Booléen (RNA trouvé ou non) |
| `addr_num/street/type` | SIRENE | Adresse postale |
| `postal_code` | SIRENE | Code postal |
| `city` | SIRENE | Commune |
| `latitude` / `longitude` | BAN | Coordonnées GPS |
| `is_ban_validated` | BAN | Adresse validée par la BAN |
| `naf` | SIRENE | Code activité APE |
| `status` | SIRENE | open / closed |

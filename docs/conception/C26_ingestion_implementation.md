# C26 — Chantier d'ingestion : notes d'implémentation (C6/C7)

> **Statut** : livré le 23 novembre 2026.
> Ce document couvre les décisions prises et les écarts corrigés lors du chantier
> d'implémentation du module d'ingestion (livrables L1 à L5). Il ne remplace pas
> le cahier des charges C6 ; il le complète.

---

## 1. Périmètre du chantier

Le chantier ciblait l'alignement du dépôt sur les spécifications C6 (passerelle) et C7
(agents). Cinq livrables ont été définis et validés :

| Livrable | Fichier(s) modifié(s) ou créé(s) | Résultat |
|---|---|---|
| L1 | `migrations/versions/0003_sources_credentials.py` | Créé — aligne `config.sources` sur le schéma courant et crée `config.source_credentials` |
| L2 | `services/baolsec-api/src/baolsec_api/routers/sources.py` | Corrigé — préfixe `bsk_` manquant dans `rotate_credential` |
| L3 | `agents/fluent-bit/linux/fluent-bit.conf`, `parsers.conf`, `windows/fluent-bit.conf` | Mis à jour — avis de redirection vers les fichiers YAML actifs |
| L4 | `compose.yaml` (racine) | Reécrit — `gateway` → `ingestion-gateway`, env, ports, TLS, healthcheck, réseaux alignés |
| L5 | `agents/README.md` | Validé comme complet — aucune modification nécessaire |

La vérification finale (Phase 5) a confirmé que le contrat `raw_event/v1`
(`shared/contracts/raw_event/v1/schema.json`) est intégralement couvert par la
passerelle telle qu'implémentée.

---

## 2. Migration 0003 — `config.sources` et `config.source_credentials`

### Contexte

La migration 0001 avait créé `config.sources` avec les colonnes `type`, `active` et
une colonne JSONB `config` libre. Le schéma courant attendu par la passerelle et l'API
utilise des noms différents et des colonnes typées distinctes.

### Upgrade

La migration 0003 (`down_revision = "0002"`) effectue dans l'ordre :

1. Renomme `type` → `source_type` et `active` → `is_enabled`.
2. Ajoute les colonnes `transport`, `ingestion_mode`, `criticality`,
   `expected_min_events_per_h` et `host`.
3. Supprime la colonne JSONB `config` (désormais remplacée par les colonnes typées).
4. Crée la table `config.source_credentials` avec :
   - `source_id` (FK vers `config.sources`) ;
   - `secret_hash` (SHA-256 du jeton `bsk_*`, stocké à la place du jeton brut) ;
   - une contrainte `CHECK (secret_hash ~ '^[0-9a-f]{64}$')` ;
   - deux index (`source_id`, `secret_hash`).
5. Accorde `SELECT` sur `config.source_credentials` au rôle `svc_passerelle`.

### Downgrade

Le downgrade est symétrique : il supprime `config.source_credentials`, recrée la
colonne JSONB `config`, renomme les colonnes dans l'ordre inverse, et supprime les
colonnes ajoutées.

La colonne `config` apparaît à la fois dans la section "ajout" (downgrade) et dans la
section "suppression" (upgrade) : c'est intentionnel, car 0001 l'avait créée et 0003
la remplace par des colonnes explicites.

---

## 3. Passerelle d'ingestion (`ingestion-gateway`)

### Contrat `raw_event/v1` — couverture confirmée

La vérification croisée entre `build_raw_event()` et le schéma JSON a confirmé que
tous les champs requis sont présents :

| Champ racine requis | Source dans `build_raw_event()` |
|---|---|
| `contract` | littéral `"raw_event/v1"` |
| `event_id` | `uuid4()` |
| `source.id` | token résolu dans le registre |
| `source.type` | champ `source_type` du registre |
| `source.ingestion_mode` | champ `ingestion_mode` du registre |
| `transport` | littéral `"https"` (HTTP) ou `"syslog"` (entrée Syslog TLS) |
| `received_at` | horodatage de réception à la passerelle |
| `payload_format` | détecté ou déclaré par l'agent (`text` / `json` / `xml`) |
| `payload` | corps de l'événement brut (tronqué à 65 536 caractères si nécessaire) |

La limite `max_event_chars = 65 536` dans `config.py` correspond exactement à
`payload.maxLength: 65536` dans le schéma.

### Authentification des sources

Les jetons de source ont le format `bsk_<32 octets URL-safe base64>`. Seul le hash
SHA-256 est stocké dans `config.source_credentials`. La correction L2 assurait que
`rotate_credential` préfixait bien `bsk_` avant de hacher.

### Ports exposés

| Port | Protocole | Usage |
|---|---|---|
| 8443 | HTTPS (TLS) | Réception des événements via agents Fluent Bit (C6 §3) |
| 6514 | Syslog TLS (RFC 5425) | Équipements émettant en Syslog avec certificat client (C6 §4) |
| 9000 | HTTP interne | Point de santé (`/health`), non exposé hors conteneur |

### Limites de débit

Jeton seau par source : 500 événements/s, rafale 5 000. Paramètre
`GATEWAY_RATE_LIMIT_EVENTS_PER_S` dans `config.py`.

---

## 4. Alignement `compose.yaml` racine

### Écarts corrigés

Le fichier `compose.yaml` à la racine du dépôt était désynchronisé du fichier de
référence `infrastructure/compose/compose.yaml`. Les écarts constatés et corrigés :

| Paramètre | Avant (erroné) | Après (correct) |
|---|---|---|
| Nom du service | `gateway` | `ingestion-gateway` |
| Variable broker URL | `NATS_URL` | `BROKER_URL` |
| Variable token broker | `NATS_TOKEN` | `BROKER_TOKEN` |
| Port HTTPS | `8080` | `8443` |
| Port Syslog | `5514` | `6514` |
| Profil Docker Compose | `profiles: ["todo"]` | aucun profil (service actif) |
| Nom du service normalisation | `normalizer` | `normalization-worker` |
| Variables normalisation | `NATS_URL` / `NATS_TOKEN` | `BROKER_URL` / `BROKER_TOKEN` |
| TLS (volumes, env) | absent | présent |
| Healthcheck | absent | présent |

### Choix de topologie réseau

Le fichier racine utilise les réseaux `baolsec-ingest` et `baolsec-data` (et non le
réseau unique `internal` du fichier `infrastructure/compose/`). C'est intentionnel :

- `baolsec-ingest` : réseau des agents et de la passerelle (ports exposés 8443/6514) ;
- `baolsec-data` : réseau du broker NATS, de PostgreSQL et des workers.

La passerelle appartient aux deux réseaux pour accéder au broker tout en restant
joignable depuis les agents. Cette topologie reflète la séparation définie dans
l'en-tête du fichier `compose.yaml`.

### Cible du broker

Dans `compose.yaml` racine, le service broker s'appelle `nats` (non `broker` comme dans
`infrastructure/compose/`). La variable `BROKER_URL` vaut donc `nats://nats:4222`.

### Volume TLS en développement

```
./infrastructure/tls/dev:/run/baolsec/dev:ro
```

Les certificats de développement (`gateway.crt`, `gateway.key`, `sources-ca.crt`) sont
montés en lecture seule depuis `infrastructure/tls/dev/`. Les variables d'environnement
`GATEWAY_TLS_CERT`, `GATEWAY_TLS_KEY` et `GATEWAY_SYSLOG_CLIENT_CA` pointent sur ce
chemin.

### Services toujours sous profil `todo`

Les services `enricher` et `rule-engine` restent sous `profiles: ["todo"]` car non
implémentés. Ils conservent les anciennes variables `NATS_URL`/`NATS_TOKEN` : à corriger
lors de leur implémentation.

---

## 5. Agents Fluent Bit (C7)

### Fichiers `.conf` — avis de redirection

Fluent Bit 5.x charge les fichiers YAML par défaut. Les fichiers `.conf` historiques
(`fluent-bit.conf`, `parsers.conf`) ont été conservés avec un avis de redirection :

```
# Ce fichier n'est pas utilisé.
# La configuration active est fluent-bit.yaml […]
# Fluent Bit 5.x charge les fichiers YAML par défaut ; voir C7 §3 et agents/README.md.
```

Les fichiers YAML actifs par plateforme sont listés dans `agents/README.md`.

### Principe de conservation — 72 heures

L'objectif de conservation sans perte est de 72 heures d'indisponibilité de la
passerelle. Le mécanisme repose sur :

1. **Tampon disque Fluent Bit** (`storage.type: filesystem`) — les événements ne sont
   retirés du tampon qu'après la réponse 202 de la passerelle.
2. **Réessais sans limite** (`retry_limit: no_limits`), délai croissant 2 s → 30 s.
3. **Limite de taille** (`BAOLSEC_BUFFER_LIMIT`, 1 Gio par défaut) — au-delà, Fluent Bit
   supprime les morceaux les plus anciens.

Le dimensionnement et la vérification (test accéléré) sont prévus dans C27.

---

## 6. Points ouverts

| Référence | Description | Action requise |
|---|---|---|
| `enricher` | Service sous `profiles: ["todo"]`, variables `NATS_URL`/`NATS_TOKEN` obsolètes | Renommer les variables lors de l'implémentation |
| `rule-engine` | Même état ; le Dockerfile est dans `services/detection-worker/` | Renommer le service ou le Dockerfile lors de l'alignement |
| C27 | Mesures de débit et de taille réels par source | Chantier C27 |
| `make test-agents` | Les résultats du tableau de conservation (`agents/README.md` §5) sont des cibles, pas des mesures validées | Valider lors de C27 |

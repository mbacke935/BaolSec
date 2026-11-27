# C26 — A-13 et A-14 : parcours de gestion des sources dans BaolSec Nexus

Date : 24 novembre 2026.

## A-14 — harmonisation du chemin `/ingest` : rien à corriger, constat de l'audit non confirmé

Recherche exhaustive de `api/v1/ingest` dans tout le dépôt (code, docs `.md`, documents
de conception `.docx` via `pandoc`, frontend) : **aucune occurrence**. Le document C6
(`C6_Passerelle_ingestion_BaolSec.docx`) mentionne déjà explicitement « HTTPS POST
/ingest 8443 », cohérent avec l'implémentation réelle (`services/ingestion-gateway/src/gateway/http/__init__.py`,
`@app.post("/ingest")`) et avec les agents (`agents/fluent-bit/common/gateway-output.yaml`,
`uri: /ingest`). Le frontend ne code en dur aucun chemin d'ingestion (il gère uniquement
les métadonnées de source, pas la configuration des agents). **Aucune incohérence
trouvée** : ce point de l'audit ne s'applique plus à l'état actuel du dépôt — corrigé
dans une session antérieure, ou jamais réellement présent sous cette forme. Classification
de l'audit rectifiée en conséquence ; aucun fichier modifié pour A-14.

## A-13 — parcours de provisionnement des sources : lacune réelle et confirmée

Audit du frontend (`frontend/src/pages/SourcesPage.tsx`, 484 lignes) et de l'API
(`services/baolsec-api/src/baolsec_api/routers/sources.py`) :

### Ce qui existe

- `POST /sources` crée l'enregistrement de la source (nom, type, transport, criticité,
  etc.) — **sans aucun identifiant d'authentification**. Confirmé par lecture du corps
  de la requête SQL : aucune colonne de `config.source_credentials` n'y est renseignée.
- `POST /sources/{id}/credentials/rotate` crée un jeton `bsk_...`, affiché une seule fois
  dans la réponse JSON (`"token": token`) — mécanisme correct et déjà testé (A-03).
  **Mais ce mécanisme ne produit que des identifiants `credential_type='token'`.**
- `DELETE /sources/{id}/credentials/{credential_id}` révoque un identifiant existant,
  quel que soit son type.

### Ce qui manque, confirmé par lecture directe du code (pas une supposition)

1. **`SourcesPage.tsx` n'appelle jamais aucune route `/credentials`.** Recherche des
   mots « credential », « rotate », « token », « fingerprint », « cert » dans ce fichier :
   **zéro occurrence**. Le formulaire de création de source (`transport: 'https' |
   'syslog'`, visible dans le state du formulaire) ne déclenche donc, après la création
   d'une source HTTPS, ni appel à `/credentials/rotate`, ni affichage du jeton à
   l'opérateur. **Un token n'est donc aujourd'hui jamais provisionné ni affiché depuis
   l'interface** — contrairement à ce que l'audit supposait possible mais non vérifié.
2. **Aucune route API n'existe pour enregistrer un identifiant `credential_type='client_cert'`
   (certificat/empreinte).** `rotate_credential` est câblé en dur sur `'token'`
   (`INSERT INTO config.source_credentials (source_id, credential_type, secret_hash)
   VALUES (%s, 'token', %s)`). Une source `transport='syslog'` (pfSense, tout équipement
   Syslog TLS) n'a donc **aucun moyen**, ni par l'API ni par le frontend, de se voir
   attribuer un `cert_fingerprint` — le seul mécanisme d'authentification que la Gateway
   sait vérifier pour ce transport (`gateway/sources_cache/__init__.py::by_fingerprint`).
   Un tel credential ne peut aujourd'hui être créé que par insertion SQL directe (seed,
   migration, ou accès direct à PostgreSQL), hors de toute interface opérateur.

### Pourquoi ce n'est pas corrigé dans cette phase sans validation préalable

Le référentiel architectural impose de m'arrêter et d'exposer les options quand une
décision technique est ambiguë plutôt que de décider unilatéralement. Combler ce point
revient à construire une fonctionnalité qui n'existe pas encore (pas un bug à corriger
dans une fonctionnalité existante comme A-01/A-03/A-05), avec plusieurs choix de
conception réels :

- **Pour le token HTTPS** : le frontend doit-il appeler `/credentials/rotate`
  automatiquement à la création de la source (token généré et affiché immédiatement,
  en un seul écran), ou seulement sur une action explicite de l'opérateur (bouton
  « Générer un jeton » séparé, après la création) ? Le second préserve mieux le principe
  « le jeton n'est affiché qu'une seule fois » en laissant l'opérateur choisir le bon
  moment (ex. juste avant de configurer l'agent), mais ajoute une étape.
- **Pour le certificat Syslog** : BaolSec doit-il **générer** un certificat client (et
  sa clé privée) côté serveur et les proposer au téléchargement une seule fois (comme le
  jeton), ou se contenter d'un **enregistrement d'empreinte** calculée à partir d'un
  certificat généré par l'opérateur lui-même (ex. `openssl x509 -fingerprint` exécuté par
  l'opérateur, empreinte collée dans un formulaire) ? Le premier est plus proche de
  l'expérience du jeton (tout généré par BaolSec) mais introduit la question de la
  distribution sécurisée d'une clé privée par le réseau ; le second est plus simple à
  implémenter et évite ce risque, mais suppose que l'opérateur sache générer un
  certificat — à documenter dans `agents/README.md` si retenu.
- **Nouvel endpoint nécessaire dans les deux cas** : soit généraliser
  `POST /{id}/credentials/rotate` avec un paramètre de type, soit créer une route dédiée
  `POST /{id}/credentials/cert` distincte de la rotation de jeton (sémantiques différentes :
  un certificat n'est pas « tourné » de la même façon qu'un jeton, et n'a pas la même
  propriété de rotation en deux temps puisqu'il n'est pas généré par le serveur dans
  l'option « empreinte seule »).

Ces choix touchent la sécurité (distribution de clé privée), le frontend, l'API et
potentiellement le modèle de données (`config.source_credentials` gère déjà les deux
types, donc pas de migration nécessaire a priori, mais à confirmer selon l'option
retenue). Conformément au référentiel (« Si une décision technique est ambiguë,
arrête-toi, expose les options, les conséquences et propose la décision la plus
cohérente avec notre socle »), ce point est soumis à validation avant implémentation.

## Décision (validée le 24/11/2026)

- **Token HTTPS : action explicite séparée.** La source est créée sans jeton. Un bouton
  « Générer un jeton », distinct de la création, appelle `POST
  /{id}/credentials/rotate` quand l'opérateur est prêt (ex. juste avant de configurer
  l'agent). Préserve au mieux le principe « le jeton n'est affiché qu'une seule fois ».
- **Certificat Syslog : empreinte saisie par l'opérateur.** BaolSec ne génère ni
  certificat ni clé privée. L'opérateur génère lui-même son certificat (ex. `openssl`),
  calcule l'empreinte SHA-256 et la colle dans un formulaire dédié. Nouvel endpoint à
  créer : `POST /{id}/credentials/cert` (ou équivalent), qui stocke uniquement le
  `cert_fingerprint` fourni — jamais de clé privée transmise ni conservée côté BaolSec.
- **Portée pour cette phase : documentation de la décision uniquement.**
  L'implémentation (nouvel endpoint, flux frontend : bouton de génération de jeton,
  formulaire de saisie d'empreinte) est **volontairement non réalisée ici**, sur
  demande explicite — à reprendre dans une session ultérieure, décision déjà actée pour
  cadrer ce travail futur.

## Implémentation (réalisée le 24/11/2026, sur instruction explicite « poursuis »)

Conformément à la décision ci-dessus, et sans y déroger :

### Backend (`services/baolsec-api`)

- `models.py` : nouveau modèle `CertCredentialCreate` (champ `cert_fingerprint`, validé
  et normalisé par un `field_validator` — minuscules, séparateurs `:`/espaces retirés,
  doit correspondre à `[0-9a-f]{64}` après normalisation, sinon `422`).
- `routers/sources.py` : nouvelle route `POST /{source_id}/credentials/cert` (import de
  `CertCredentialCreate` ajouté). Vérifie que la source existe (`404` sinon) et que son
  `transport` est `'syslog'` (`422` sinon — un certificat client n'a pas de sens pour une
  source HTTPS authentifiée par jeton), puis insère une ligne `config.source_credentials`
  avec `credential_type='client_cert'` et l'empreinte normalisée. Aucune clé privée
  générée ni demandée : conforme à la décision « empreinte saisie par l'opérateur ».
- `tests/test_routes.py` : 4 nouveaux tests dans `TestSources` — normalisation/stockage
  de l'empreinte, rejet d'une empreinte invalide (422), rejet pour une source `https`
  (422), source introuvable (404). Les 4 passent isolément et dans la suite complète.
- Suite complète ré-exécutée après ces changements : **36 passed, 6 failed** (les 6
  échecs sont le défaut `paginate()` pré-existant et documenté dans
  `C26_audit_C6C7_phase1_corrections.md`, sans rapport avec A-13 — aucune régression).

### Frontend (`frontend/src/pages/SourcesPage.tsx`)

- Nouveau composant `CredentialsModal`, ouvert via un bouton « Identifiants » ajouté à
  chaque ligne du tableau des sources (nouvelle colonne). Il affiche la liste des
  identifiants existants de la source (`GET /{id}/credentials` : type, empreinte, date de
  création, statut actif/révoqué), avec un bouton « Révoquer » par identifiant actif
  (`DELETE /{id}/credentials/{credential_id}`).
- Pour une source `transport: 'https'` : bouton **« Générer un jeton »**, séparé de la
  création de la source (décision actée) — appelle `POST /{id}/credentials/rotate` et
  affiche le jeton renvoyé **une seule fois**, dans un encart d'avertissement rappelant
  qu'il ne sera plus jamais réaffiché et que les anciens jetons restent actifs tant
  qu'ils ne sont pas explicitement révoqués.
- Pour une source `transport: 'syslog'` : formulaire de saisie d'empreinte de certificat
  (champ texte + bouton « Enregistrer l'empreinte »), avec un rappel textuel que BaolSec
  ne génère ni ne conserve de clé privée et un exemple de commande `openssl` pour obtenir
  l'empreinte — appelle `POST /{id}/credentials/cert`.
- Aucun appel automatique de génération de jeton ou de certificat à la création de la
  source : conforme à la décision « action explicite séparée ».
- Validé par une compilation complète (`npm install` puis `npm run build` : `tsc` et le
  build Vite passent sans erreur ni avertissement sur les fichiers modifiés).

### Limite constatée, hors périmètre de ce point (description précisée le 24/11/2026, F-5)

Vérification directe du code, plus précise que la description initiale (« ne réutilise
pas les classes des feuilles de style ») :

- **`SourcesPage.tsx` n'importe aucune feuille de style** — ses deux seuls imports sont
  `react` et le client API (`import { useState, useEffect, useCallback } from 'react';
  import { apiClient as api } from '../api/client';`, lignes 1-2 ; aucune ligne `import
  '*.css'`). La mise en forme visible de la page ne provient donc pas d'un import propre
  à ce fichier, mais de `src/styles/design-system.css`, chargé globalement par
  `AdminLayout.tsx` et `AnalystLayout.tsx` (pas par `main.tsx`, qui importe
  `maquette.css`) — le composant hérite d'un style chargé ailleurs, il ne le déclare pas
  lui-même.
- **Même ce CSS global ne définit aucune des classes de modale utilisées** :
  `bs-modal-overlay`, `bs-modal`, `bs-modal-header`, `bs-modal-title`, `bs-modal-body`,
  `bs-modal-footer`, `bs-form-grid` — zéro occurrence dans `design-system.css` (recherche
  exhaustive). Elles sont utilisées à la fois par le composant **`SourceModal`,
  préexistant** (lignes 78, 284-309, présent avant toute intervention A-13) et par le
  nouveau `CredentialsModal` (lignes 370, 438-539) : le défaut est donc identique sur les
  deux composants, et antérieur à ce travail.
- **Les badges utilisent une convention à double tiret (`bs-badge--success`,
  `bs-badge--neutral`, `bs-badge--warning`, `bs-badge--danger`, `bs-badge--critical`,
  `bs-badge--info`, `bs-badge--type`) qui ne correspond à aucune règle réelle** :
  `design-system.css` définit les variantes de `.bs-badge` par une classe seconde simple,
  sans double tiret (ex. `.bs-badge.critique`, `.bs-badge.active`), jamais
  `.bs-badge--critique`. Cette convention erronée est déjà celle du **tableau des
  sources lui-même** (lignes 550-669, code préexistant, bien avant A-13) ;
  `CredentialsModal` (lignes 521-522) ne fait que reproduire la convention déjà cassée
  ailleurs dans ce même fichier, il ne l'introduit pas.

**Conclusion** : aucune classe utilisée par `SourcesPage.tsx` (tableau, `SourceModal` ou
`CredentialsModal`) ne correspond à une règle réellement définie dans les feuilles de
style du dépôt ; l'apparence actuelle de la page dépend entièrement des styles par défaut
du navigateur. Défaut 100 % préexistant à A-13, confirmé identique sur le code déjà en
place avant cette phase ; non corrigé ici (corriger l'ensemble de la page dépasserait le
périmètre de ce constat et de F-5, qui porte sur l'harmonisation documentaire, pas sur
une refonte de style). Signalé pour une session ultérieure dédiée au style de cette page.

## F-3, F-4, F-6 (vérification complémentaire du 24/11/2026, suite à l'audit de clôture A-13)

L'audit de clôture mené après l'implémentation ci-dessus a relevé trois réserves non
bloquantes, traitées dans cet ordre sur validation explicite :

- **F-3 — unicité des identifiants actifs.** Aucune contrainte n'empêchait deux
  identifiants actifs (jeton ou certificat) de partager la même valeur
  (`secret_hash`/`cert_fingerprint`), entre deux sources différentes ou au sein d'une
  même source — risque confirmé par lecture de `gateway/sources_cache/__init__.py`
  (cache en mémoire indexé par empreinte/hash, dernière valeur gagnante en cas de
  collision, sans erreur ni log : un doublon aurait pu attribuer silencieusement des
  événements à la mauvaise source). Corrigé par la migration
  `migrations/versions/0004_credentials_unicite.py` : deux index uniques partiels,
  scopés aux identifiants **actifs** (`WHERE revoked_at IS NULL`), pour ne pas bloquer la
  réutilisation d'une valeur après révocation explicite (cohérent avec le cycle de
  rotation en deux temps déjà en place, A-03). `routers/sources.py`
  (`rotate_credential`, `add_cert_credential`) intercepte désormais une violation de
  contrainte unique et renvoie `HTTP 409` au lieu de laisser remonter une erreur 500 non
  gérée. Vérifié avant application que le jeu de données de développement
  (`infrastructure/tls/dev/sources.json`) ne contenait aucun doublon actif — la migration
  documente elle-même que cette vérification est ponctuelle (dev uniquement) et devra
  être refaite avant application sur une base réelle. 3 nouveaux tests dans
  `tests/test_routes.py` (doublon de certificat → 409, doublon de jeton → 409,
  réutilisation après révocation → 201).
- **F-4 — tests réels de handshake TLS.** Les tests existants (A-01, A-06) simulaient le
  certificat client via un objet `_FakeSSLObject` qui ne fait jamais passer de poignée de
  main TLS réelle — l'audit a explicitement rappelé de ne pas considérer
  l'enregistrement d'une empreinte comme une preuve de fonctionnement mTLS. Nouveau
  fichier isolé `services/ingestion-gateway/tests/test_tls_handshake.py` (3 tests) :
  ouvre un vrai serveur TCP/TLS construit avec `gateway.syslog.tls_context()` (code de
  production inchangé) et des certificats réels générés en mémoire (bibliothèque
  `cryptography`), démontrant qu'un certificat signé par l'AC de confiance est accepté
  (avec l'empreinte SHA-256 réellement vue côté serveur), qu'un certificat signé par une
  autre AC est refusé, et qu'une connexion sans certificat client est refusée.
  **Important** : ces tests valident le comportement cryptographique du code actuel ; ils
  ne tranchent rien sur le modèle de confiance encore en attente d'arbitrage (voir
  « Décision non encore arbitrée » ci-dessous).
- **F-6 — test RBAC direct pour l'enregistrement d'un certificat.** Seule la route
  `/credentials/rotate` disposait d'un test RBAC explicite ; `/credentials/cert` n'était
  exercée par aucun test vérifiant qu'un rôle ANALYSTE reçoit bien `403`. Nouveau test
  `test_post_cert_credential_only_admin` dans `TestSourcesRBAC`
  (`services/baolsec-api/tests/test_rbac.py`), matrice de droits du fichier mise à jour
  en conséquence.

Résultats réels, suites complètes ré-exécutées après F-3/F-4/F-6 (aucun test existant
modifié ou supprimé) :

| Suite | Résultat |
|---|---|
| `services/ingestion-gateway` | **51 PASSED** (48 + 3 nouveaux tests F-4) |
| `services/baolsec-api` | **40 PASSED, 6 FAILED** (36 + 4 nouveaux tests F-3/F-6 ; les 6 échecs restent le défaut `paginate()` pré-existant, documenté, non corrigé sur instruction explicite) |

## Décision non encore arbitrée : modèle de confiance mTLS (F-2)

L'audit de clôture a relevé que la décision actée le 24/11/2026 ci-dessus
(« l'opérateur génère lui-même son certificat ») ne précise pas **comment** ce
certificat devient effectivement approuvé par le mécanisme TLS réel
(`load_verify_locations(client_ca)`, qui charge un fichier unique). Deux modèles ont été
présentés et restent en attente d'arbitrage explicite, **aucun n'est retenu à ce
stade** :

1. l'opérateur génère un certificat auto-signé et BaolSec l'ajoute individuellement à un
   faisceau de certificats de confiance (`sources-ca.crt` devient une liste de
   certificats approuvés un par un, pas une AC) ;
2. BaolSec exploite une AC dédiée qui signe les certificats soumis par les opérateurs
   (`sources-ca.crt` reste une AC unique, cohérent avec le code actuel, mais introduit la
   responsabilité de protéger la clé privée de cette AC).

**Aucun code, migration ou flux frontend lié à ce choix ne doit être considéré comme
implémenté ou définitif tant que cet arbitrage n'a pas eu lieu.** Les tests F-4
ci-dessus valident uniquement que le mécanisme TLS actuel vérifie cryptographiquement un
certificat client contre le contenu de `client_ca` — un fait vrai quel que soit le modèle
finalement retenu pour construire ce fichier, pas une validation du modèle lui-même.

## Statut

**A-14** : vérifié, aucune action nécessaire.
**A-13** : lacune initiale confirmée (pas de provisionnement de token depuis le
frontend, pas d'endpoint pour les certificats Syslog) ; décision de conception actée
pour le **provisionnement** (ci-dessus) et **implémentée** le 24/11/2026 (backend +
frontend) ; **durcie** le même jour par F-3 (unicité), F-4 (tests TLS réels) et F-6
(RBAC direct). Le **modèle de confiance mTLS sous-jacent (F-2)** reste en revanche
**non arbitré** (section ci-dessus) : à ce titre, A-13 n'est pas une clôture définitive
mais une implémentation du provisionnement conforme à une décision qui pourrait encore
évoluer selon l'arbitrage F-2. Tests exécutés et réellement passants (détail ci-dessus) ;
aucune régression sur les suites `baolsec-api` et `ingestion-gateway`.

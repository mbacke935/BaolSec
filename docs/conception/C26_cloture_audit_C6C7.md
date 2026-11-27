# C26 — Clôture de l'audit C6/C7 (A-01 à A-15)

Date : 24 novembre 2026. Document de synthèse finale, à lire avec les documents
détaillés par constat (`C26_audit_C6C7_phase1_corrections.md`,
`C26_event_id_limite_json.md`, `C26_A06_revocation_cache.md`,
`C26_A07_A08_A11_collecte_buffering.md`, `C26_A09_A10_validation.md`,
`C26_A13_A14_parcours_sources.md`, `C26_A15_confidentialite.md`).

## Tableau de synthèse

| # | Constat | Statut | Nature |
|---|---|---|---|
| A-01 | Trames Syslog trop longues non en DLQ | **Corrigé, testé** | Défaut confirmé |
| A-02 | Rate limiter : lot > rafale | **Classification corrigée** | Constat d'audit inexact — mécanisme intentionnel déjà testé |
| A-03 | Rotation/révocation tokens incohérente | **Corrigé, testé** | Défaut confirmé |
| A-04 | event_id : timestamp agent exclu | **Décision actée (Option A), documentée, testée** | Limite conditionnelle, pas un défaut avéré sur les sources actuelles |
| A-05 | Publication concurrente non bornée | **Corrigé, testé** | Défaut confirmé |
| A-06 | Cache source / révocation | **Tests ajoutés, mécanisme déjà correct** | Couverture de test manquante, pas un défaut de code |
| A-07 | pfSense UDP sans ACK | **Déjà documenté dans C7, vérifié** | Constat d'audit déjà couvert ; limite intrinsèque, test de charge hors périmètre |
| A-08 | Objectif 72h / buffer | **Dimensionnement déjà documenté ; 2 bugs d'observabilité trouvés et corrigés** | Prometheus ne scrutait pas réellement la Gateway ni le Normalization Worker |
| A-09 | Validation Fluent Bit (`make agents-check`) | **Toujours bloqué (pas de démon Docker)** | Blocage d'environnement confirmé, vérification YAML partielle effectuée |
| A-10 | Tests Gateway non exécutables | **Résolu** | Environnement pytest reconstruit ; corrigé le 24/11/2026 (F-5) : ce décompte était resté figé à une étape intermédiaire et ne reflétait déjà plus l'état réel au moment de la rédaction de ce tableau. Décompte réel au 24/11/2026 (après F-3/F-4/F-6, voir tableau « Résultats de test finaux » révisé plus bas) : 51/51 (gateway), 40/6 (api, défaut `paginate()` pré-existant, non corrigé) |
| A-11 | Statut tests réels Windows/pfSense | **Déjà documenté dans C7, vérifié** | Constat d'audit déjà couvert |
| A-12 | `agents/README.md` trop succinct | **Complété** | Désinstallation, TLS, rotation, dépannage ajoutés |
| A-13 | Parcours de provisionnement des sources (Nexus) | **Lacune confirmée ; décision actée ; implémenté et testé ; durci par F-3/F-4/F-6 ; modèle de confiance mTLS sous-jacent (F-2) non arbitré** | Nouvel endpoint `POST /{id}/credentials/cert` (backend) + UI de génération de jeton et de saisie d'empreinte (frontend), conformes à la décision validée le 24/11/2026 ; voir addendum ci-dessous pour F-2 |
| A-14 | Harmonisation du chemin `/ingest` | **Vérifié, aucune incohérence trouvée** | Constat d'audit non confirmé dans l'état actuel du dépôt |
| A-15 | `.env` dans l'archive | **Vérifié, absent de cette archive (`baolsec_tar_5.xz`)** | Rien à purger pour cette archive précise — **conclusion corrigée depuis** : une archive livrée ultérieurement (`baolsec_corrige_A13_complet.tar.xz`) contenait bien des clés privées et des secrets réels (constat F-1, 24/11/2026) ; voir `C26_A15_confidentialite.md`, section « Correction », et l'addendum ci-dessous |

## Ce qui a été modifié (code et configuration, hors documentation)

| Fichier | Constat | Nature |
|---|---|---|
| `services/ingestion-gateway/src/gateway/syslog/__init__.py` | A-01 | Production |
| `services/ingestion-gateway/src/gateway/publisher/__init__.py` | A-05 | Production |
| `services/baolsec-api/src/baolsec_api/routers/sources.py` | A-03, A-13, F-3 | Production |
| `services/baolsec-api/src/baolsec_api/models.py` | A-13 | Production |
| `frontend/src/pages/SourcesPage.tsx` | A-13 | Production |
| `migrations/versions/0004_credentials_unicite.py` | F-3 | Production (migration, nouveau) |
| `services/ingestion-gateway/tests/test_units.py` | A-04 | Test |
| `services/ingestion-gateway/tests/test_syslog.py` | A-01, A-06 | Test |
| `services/ingestion-gateway/tests/test_http.py` | A-05, A-06 | Test |
| `services/ingestion-gateway/tests/test_publisher.py` | A-05 | Test (nouveau) |
| `services/ingestion-gateway/tests/test_tls_handshake.py` | F-4 | Test (nouveau) |
| `services/baolsec-api/tests/test_routes.py` | A-03, A-13, F-3 | Test |
| `services/baolsec-api/tests/test_rbac.py` | F-6 | Test |
| `docker/prometheus/prometheus.yml` | A-08 | Configuration |
| `compose.yaml` | A-08 | Configuration |
| `agents/README.md` | A-12 | Documentation opérationnelle |

Tout le reste du travail de cette phase (et de la vérification complémentaire F-1 à F-6,
hors F-3/F-4/F-6 listés ci-dessus) est de la documentation de conception
(`docs/conception/C26_*.md`), sans impact sur le comportement du système.

## Résultats de test finaux (ré-exécutés en clôture — **obsolètes**, voir révision ci-dessous)

| Suite | Résultat |
|---|---|
| `services/ingestion-gateway` | **48/48 PASSED** |
| `services/baolsec-api` | **36 PASSED, 6 FAILED** (défaut `paginate()` pré-existant, hors périmètre, non corrigé sur instruction explicite, documenté dans `C26_audit_C6C7_phase1_corrections.md` — 4 nouveaux tests A-13 inclus parmi les passants) |
| `frontend` (`tsc` + `vite build`) | **Build réussi**, aucune erreur de type ni d'avertissement sur les fichiers modifiés (A-13) |

Aucun test supprimé, désactivé ou affaibli pour obtenir une suite artificiellement
verte, à aucun moment de cette phase.

### Révision (24/11/2026, F-5) — résultats réels après la vérification complémentaire F-3/F-4/F-6

Le tableau ci-dessus correspond à l'état du dépôt **avant** la phase de vérification
approfondie qui a suivi cette clôture (voir « Addendum » ci-dessous). Il est conservé
tel quel pour l'historique, mais ne doit plus être cité comme l'état actuel. Décompte
réel, ré-exécuté le 24/11/2026 après F-3 (migration 0004, unicité), F-4 (tests TLS
réels) et F-6 (RBAC direct) :

| Suite | Résultat |
|---|---|
| `services/ingestion-gateway` | **51 PASSED** (48 + 3 nouveaux tests F-4, `test_tls_handshake.py`) |
| `services/baolsec-api` | **40 PASSED, 6 FAILED** (36 + 4 nouveaux tests F-3/F-6 ; les 6 échecs sont **exactement** les mêmes `paginate()` `KeyError: 0` qu'avant — non corrigés, conformément à l'instruction explicite de ne pas les traiter dans cette phase) |

Aucun test existant modifié, supprimé ou désactivé pendant F-3/F-4/F-6.

## Limites de validation à connaître (persistantes)

- Aucun test d'intégration réel (PostgreSQL, NATS JetStream, Docker Compose complet)
  n'a pu être exécuté dans cet environnement : pas de démon Docker actif. Toutes les
  vérifications reposent sur des tests unitaires avec doubles de test, et pour certains
  points (A-03, A-06, A-08) sur un traçage de code à travers les implémentations réelles
  plutôt que sur une exécution bout en bout.
- `make agents-check` (A-09) reste bloqué pour la même raison.
- Les tests réels sur agent Windows et équipement pfSense (A-11) restent hors de portée
  de tout environnement de travail purement logiciel — déjà renvoyés à C27 par C7
  lui-même, pas une omission de cette phase.
- A-13 est désormais implémenté (backend + frontend) conformément à la décision validée
  le 24/11/2026, puis durci par F-3/F-4/F-6 ; voir `C26_A13_A14_parcours_sources.md` pour
  le détail complet et à jour. **Précision (24/11/2026, F-5)** : le défaut de style de
  `SourcesPage.tsx` n'est pas une simple incohérence de vocabulaire de classes — le
  fichier n'importe aucune feuille de style, et même le CSS global dont il hérite
  (`design-system.css`, chargé par les layouts) ne définit aucune des classes de modale
  utilisées (`bs-modal-*`, `bs-form-grid`), ni les variantes de badge à double tiret
  (`bs-badge--*`) employées par le tableau des sources et les deux modales. Défaut
  intégralement préexistant (confirmé identique sur le composant `SourceModal`, avant
  toute intervention A-13), non introduit et non corrigé ici (hors périmètre de ce
  constat).
- **Le modèle de confiance mTLS sous-jacent à A-13 (F-2) reste non arbitré.** La décision
  actée le 24/11/2026 ne précise pas comment un certificat opérateur devient
  effectivement approuvé par le mécanisme TLS réel (`load_verify_locations`) ; deux
  modèles ont été présentés et aucun n'est retenu à ce stade. Voir
  `C26_A13_A14_parcours_sources.md`, section « Décision non encore arbitrée », et
  l'addendum ci-dessous.

## Addendum (24/11/2026) — vérification de clôture complémentaire et réserves

Une phase de vérification approfondie, distincte de cette clôture initiale, a été menée
après la rédaction de ce document et a abouti à un verdict de **CLÔTURE CONDITIONNELLE**,
pas une validation inconditionnelle. Deux réserves bloquantes (**F-1**, **F-2**) et
quatre réserves non bloquantes (**F-3** à **F-6**) ont été identifiées :

| # | Réserve | Statut au 24/11/2026 |
|---|---|---|
| F-1 | Archive livrée contenant des clés privées et secrets réels (voir `C26_A15_confidentialite.md`, section « Correction ») | **Résolu** — nouvelle archive (`baolsec_corrige_A13_v2_sans_secrets.tar.xz`) construite, vérifiée deux fois, livraison autorisée |
| F-2 | Modèle de confiance mTLS A-13 non précisé (deux options possibles, aucune choisie) | **Non résolu, en attente d'arbitrage explicite** — aucun code ni décision définitive |
| F-3 | Absence de contrainte d'unicité sur les identifiants actifs | **Résolu** — migration 0004, gestion HTTP 409, 3 tests |
| F-4 | Absence de test de handshake TLS réel | **Résolu** — `test_tls_handshake.py`, 3 tests |
| F-5 | Incohérences documentaires (ce document, `C26_A15_confidentialite.md`, `C26_A13_A14_parcours_sources.md`) | **Résolu** — présente mise à jour |
| F-6 | Absence de test RBAC direct sur `/credentials/cert` | **Résolu** — `test_post_cert_credential_only_admin` |

**Statut d'ensemble au 24/11/2026 : CLÔTURE CONDITIONNELLE.** F-1 et F-3/F-4/F-6 sont
résolus et vérifiés ; **F-2 reste explicitement en attente** et n'a reçu aucune décision
définitive. La section « Clôture » ci-dessous, rédigée avant cette vérification
complémentaire, ne doit donc plus être lue comme une clôture inconditionnelle de
l'audit C6/C7 — elle reste correcte pour les constats A-01 à A-15 qu'elle couvrait
alors, mais ne couvre pas les réserves F-1/F-2 découvertes ensuite.

## Conformité au référentiel architectural

Aucune décision architecturale listée en section 10 du référentiel n'a été remise en
cause (NATS JetStream, ECS, OpenSearch, PostgreSQL, React/Vite, Docker Compose,
BaolSec Nexus). Aucun service n'a été fusionné, aucun contrat de stream modifié, aucune
migration touchée. Les deux seules corrections dépassant le périmètre strict des
constats A-01 à A-15 (les noms d'hôte/ports Prometheus et la variable d'environnement du
port de métriques, découverts en vérifiant la faisabilité d'alertes buffer pour A-08)
sont des corrections de configuration mécaniques et bornées, vérifiées par lecture
croisée des noms de service et des ports réels — pas des décisions architecturales.

## Clôture (A-01 à A-15, telle que rédigée le 24/11/2026 — à lire avec l'addendum ci-dessus)

Toutes les phases alors demandées (Phase 1 à Phase 6, couvrant les constats A-01 à A-15)
étaient terminées à la rédaction de ce document.

**Ce paragraphe ne doit plus être lu comme une clôture inconditionnelle de l'audit
C6/C7.** Une vérification complémentaire menée après cette rédaction a relevé des
réserves supplémentaires (F-1 à F-6, voir addendum ci-dessus) non couvertes par les
constats A-01 à A-15 eux-mêmes. À la date de cette révision (24/11/2026) :
- F-1, F-3, F-4, F-5, F-6 sont résolus et vérifiés ;
- **F-2 (modèle de confiance mTLS A-13) reste explicitement en attente d'arbitrage** —
  aucun modèle n'est retenu, aucun code n'y est lié.

Le statut réel et à jour de l'audit C6/C7 est donc **CLÔTURE CONDITIONNELLE**, pas une
clôture définitive, tant que F-2 n'a pas été tranché. L'archive à livrer est l'archive
v2 vérifiée (`baolsec_corrige_A13_v2_sans_secrets.tar.xz`, voir `C26_A15_confidentialite.md`)
et non l'archive antérieure mentionnée implicitement par la phrase d'origine de ce
paragraphe.

## Note (27/11/2026) — emplacement de la migration F-3

La chaîne de migrations `migrations/` à la racine divergeait de la chaîne officielle
`infrastructure/database` (celle qu'exécutent `make db-up` et le service `db-migrate`). Elle a été
supprimée ; la contrainte F-3 se trouve désormais dans
`infrastructure/database/sql/0009_credentials_unicite.sql` (révision `0009`). Les mentions de
`migrations/versions/0004_credentials_unicite.py` ci-dessus renvoient à cette révision : index unique
partiel sur `secret_hash` des identifiants actifs ; l'unicité de `cert_fingerprint` est déjà
assurée par la contrainte UNIQUE de `0002` (y compris après révocation).
F-2 reste **EN ATTENTE**. Détail : `C26_audit_complet_corrections.md`.

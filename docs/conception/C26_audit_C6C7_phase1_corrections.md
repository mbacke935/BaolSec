# C26 — Audit C6/C7 : corrections Phase 1 (fiabilité et sécurité de la Gateway)

Date : 24 novembre 2026 (mise à jour après le tour de vérification approfondie demandé
en validation conditionnelle). Référence : rapport d'audit du 23/11/2026 (A-01 à A-15)
et référentiel architectural BaolSec transmis le même jour.

**Statut : Phase 1 non close.** Ce document consigne l'état des corrections et de leur
vérification ; il n'emporte à lui seul aucune clôture de phase (voir « Validation
requise » en fin de document).

## État par constat de la Phase 1

### A-01 — Trames Syslog trop longues non conservées dans la DLQ

**Confirmé et corrigé — et re-vérifié en profondeur.** `SyslogServer.handle()` ne
faisait qu'incrémenter des métriques sur `FrameTooLong` sans rien publier. Correction :

- `FrameTooLong` porte désormais `reason` et `length` (taille déclarée ou observée).
- Le handler publie un enregistrement DLQ borné (`dlq_message/v1`) avec un motif
  explicite, **sans inventer le contenu original** : celui-ci n'est jamais tamponné,
  par construction, pour ne pas exposer la passerelle à un en-tête de longueur hostile.
- Fichier : `services/ingestion-gateway/src/gateway/syslog/__init__.py`.

**Défaut trouvé et corrigé pendant la re-vérification des métadonnées DLQ** (demandée
explicitement) : la première version transmettait à `_reject_until_stored` uniquement
le texte de substitution (repère borné, ~100 caractères), dont la méthode dérivait alors
`reason` par `len(texte)` — ce qui rapportait la taille du repère, pas celle de la trame
réellement rejetée. Correction : `_reject_until_stored` accepte désormais un paramètre
`reason` explicite ; l'appelant construit ce motif à partir de `exc.reason`/`exc.length`
(la taille réelle, déclarée ou observée) avant d'invoquer le rejet.

- Tests : `tests/test_syslog.py::test_trame_trop_longue_consignee_en_dlq` (découpage par
  ligne) et `tests/test_syslog.py::test_trame_trop_longue_comptage_octets_consignee_en_dlq`
  (comptage d'octets, RFC 5425) — chacun exécute `SyslogServer.handle()` de bout en bout
  avec un broker en mémoire et vérifie : exactement un message DLQ conforme au schéma
  `dlq_message/v1`, un motif (`reason`) rapportant la taille réellement observée/déclarée
  (confirmée par exécution : 1505 octets pour le cas ligne, pas une valeur supposée a
  priori) et le mode de découpage (`"ligne"` ou `"comptage_octets"`), `attempts == 1`,
  `reason_code == "validation_error"`, `original_stream == "ingest"`, le bon `source_id`,
  et que le contenu original n'est jamais reconstitué dans le payload DLQ. Les deux tests
  vérifient aussi que la trame valide suivante est publiée normalement (la lecture
  continue sans blocage après un rejet).

### A-02 — Rate limiter : lot pouvant dépasser la rafale

**Constat de l'audit corrigé — ce n'est pas un défaut.** Le code documente (et un test
existant, `test_lot_plus_grand_que_la_rafale_jamais_bloque`, démontrait déjà) un
mécanisme de dette intentionnel : un lot peut dépasser la rafale une fois, mais la
dette résultante bloque tout lot suivant tant qu'elle n'est pas remboursée. Avec
`max_events_per_batch=50000`, `burst=5000`, `rate=500/s`, le pire cas observable est
~90s de throttle après un lot plein — borné, non un flot illimité. Aucune modification
de code. Le risque réel associé (création massive de tâches concurrentes pour un gros
lot) est traité séparément en A-05.

### A-03 — Rotation des tokens incohérente avec C7

**Confirmé et corrigé.** `rotate_credential` révoquait les jetons actifs précédents
dans la même opération que la création du nouveau, et ne préfixait pas `bsk_`
(contrairement à `gateway/auth.py::generate_token`, déjà conforme et déjà testé).
Risque réel : Fluent Bit abandonne un lot sur 401 (pas de réessai), donc une révocation
immédiate avant que l'agent ne soit reconfiguré avec le nouveau jeton perd les
événements envoyés dans l'intervalle.

Correction — rotation en deux temps, telle que recommandée par C7 :

- `POST /sources/{id}/credentials/rotate` crée un nouveau jeton `bsk_...` **sans**
  révoquer les jetons existants.
- Nouvel endpoint `DELETE /sources/{id}/credentials/{credential_id}` révoque
  explicitement un identifiant donné, une fois le nouveau jeton confirmé en place
  côté agent.
- Fichier : `services/baolsec-api/src/baolsec_api/routers/sources.py`.
- Tests ajoutés : `tests/test_routes.py::test_rotate_credential_prefixe_bsk_et_ne_revoque_pas`
  (vérifie le préfixe et l'absence de `UPDATE ... revoked_at` dans la même opération),
  `test_revoke_credential_204`, `test_revoke_credential_introuvable_404`.

Aucune UI frontend n'appelait cet endpoint (vérifié dans `frontend/src`) : ce
changement ne casse aucun parcours existant. Le parcours de gestion des sources dans
BaolSec Nexus reste à construire (A-13, hors Phase 1).

### A-04 — Identifiant d'événement : timestamp agent exclu de l'empreinte

**Décision du 24/11/2026 (option A) : comportement et contrat conservés.** Voir
`docs/conception/C26_event_id_limite_json.md` pour le détail complet de la
vérification par source et des tests ajoutés. Résumé : quatre des cinq familles de
sources C7 embarquent structurellement leur propre horodatage dans le payload ;
Windows ne passe pas par ce mécanisme (identifiant natif). `web.app` (journal
applicatif) reste une exposition réelle et déjà intégrée, conditionnée au format
choisi par l'application surveillée — documentée comme limite connue, pas corrigée.
Linux journald n'a pas pu être vérifié avec certitude sans exécution réelle de
Fluent Bit (A-09).

### A-05 — Publication concurrente non bornée

**Confirmé et corrigé — et re-vérifié en profondeur.** `publish_all()` créait toutes les
tâches du lot (jusqu'à 50 000) en une seule volée via `asyncio.gather()`. Correction :
publication par blocs bornés (`PUBLISH_CHUNK_SIZE = 500`).

- Fichier : `services/ingestion-gateway/src/gateway/publisher/__init__.py`.

**Correction de la docstring, demandée explicitement** : la première formulation
(« le lot reste tout-ou-rien côté appelant ») risquait d'être lue comme une garantie
d'atomicité côté broker, qui n'existe pas et n'a jamais existé (avant comme après le
découpage en blocs). La docstring explique désormais, en toutes lettres : le découpage
n'introduit ni ne retire aucune atomicité ; un bloc qui réussit reste durablement publié
même si un bloc suivant échoue (rien n'est « annulé ») ; la seule garantie tout-ou-rien
réelle se situe au niveau du contrat HTTP/agent (202 avec résultat durable pour chaque
événement, ou 503 et renvoi du lot complet), pas au niveau de l'écriture broker ; la
sûreté d'un renvoi complet après erreur vient de l'idempotence du Msg-Id déterministe
(event_id, ou sha256(source_id|contenu) pour les rejets), pas d'une transaction.

Tests, dont trois nouveaux dans un fichier dédié créé pendant la re-vérification :

- `tests/test_http.py::test_lot_volumineux_publie_par_blocs` — lot de 1200 événements
  (2 blocs pleins + 1 partiel) avec 7 rejets distincts répartis sur la frontière du
  dernier bloc (corrigé pendant la re-vérification : des rejets au contenu identique se
  dédupliquaient par Msg-Id et ne produisaient qu'un seul message DLQ au lieu de sept ;
  corrigé en donnant à chacun un contenu distinct) ; vérifie l'absence de perte et de
  duplication aux frontières.
- `tests/test_publisher.py` (nouveau) :
  - `test_tailles_de_lot_autour_de_la_frontiere_de_bloc` — paramétré sur n ∈
    {1, 499, 500, 501, 1000} (autour de `PUBLISH_CHUNK_SIZE`), aucun événement perdu ni
    dupliqué, quel que soit le découpage en blocs.
  - `test_erreur_en_milieu_de_lot_interrompt_les_blocs_suivants` — un lot de 3 blocs
    pleins dont le 2e échoue au milieu : le 1er bloc est intégralement publié et reste
    acquis, le 2e bloc est intégralement *tenté* (comportement réel et vérifié de
    `asyncio.gather(..., return_exceptions=True)`, qui attend toutes les tâches d'un même
    bloc avant de lever, sans les annuler), le 3e bloc n'est jamais tenté.
  - `test_renvoi_complet_apres_echec_partiel_est_sans_perte_ni_doublon` — simule le
    comportement réel de l'agent Fluent Bit sur 503 (renvoi du lot entier) : après un
    échec partiel puis un second essai complet, exactement n événements au total, aucune
    perte, aucun doublon dans le broker.

### A-02 — Rate limiter : lot pouvant dépasser la rafale

**Constat de l'audit corrigé — ce n'est pas un défaut.** Le code documente (et un test
existant, `test_lot_plus_grand_que_la_rafale_jamais_bloque`, démontrait déjà) un
mécanisme de dette intentionnel : un lot peut dépasser la rafale une fois, mais la dette
résultante bloque tout lot suivant tant qu'elle n'est pas remboursée. Avec
`max_events_per_batch=50000`, `burst=5000`, `rate=500/s`, le pire cas observable est
~90s de throttle après un lot plein — borné, non un flot illimité. Aucune modification
de code. Le risque réel associé (création massive de tâches concurrentes pour un gros
lot) est traité séparément en A-05, dont il reste distinct : A-02 concerne le débit admis
par le limiteur, A-05 la bornification de la concurrence de publication.

### A-04 — Identifiant d'événement : timestamp agent exclu de l'empreinte

**Décision du 24/11/2026 (option A) : comportement et contrat conservés — re-confirmée.**
Voir `docs/conception/C26_event_id_limite_json.md` pour le détail complet de la
vérification par source et des tests. Résumé inchangé par ce tour de re-vérification :
quatre des cinq familles de sources C7 embarquent structurellement leur propre
horodatage dans le payload ; Windows ne passe pas par ce mécanisme (identifiant natif) ;
`web.app` (journal applicatif) reste une exposition réelle et déjà intégrée, conditionnée
au format choisi par l'application surveillée — documentée comme limite connue, non
corrigée (aucun horodatage artificiel introduit, idempotence des retransmissions
préservée) ; Linux journald n'a pas pu être vérifié avec certitude sans exécution réelle
de Fluent Bit (A-09). Les deux tests dédiés (`test_json_sans_timestamp_propre_collision_connue`,
`test_json_avec_timestamp_propre_diverge`) ont été ré-exécutés dans ce tour et passent
toujours.

## Vérification exécutée (re-vérification complète, pas seulement des modifications)

| Vérification | Résultat |
|---|---|
| Diff de chaque fichier de production modifié (A-01, A-03, A-05) contre une base saine extraite de `baolsec_tar_5.xz` | **PASSED** — portée strictement limitée aux cinq constats, aucune ligne hors sujet |
| Diff de chaque fichier de test modifié contre la même base saine | **PASSED** — `test_http.py` et `test_routes.py` : 0 ligne supprimée (ajouts purs) ; `test_syslog.py` : exactement 2 lignes « supprimées », qui sont l'ancien docstring et l'ancien import mono-ligne, remplacés par leurs versions étendues (attendu, pas une suppression de logique de test) |
| Métadonnées DLQ effectivement conservées pour A-01 | **PASSED** — défaut trouvé et corrigé (voir A-01 ci-dessus) |
| Non-blocage des trames suivantes après une trame trop longue (A-01) | **PASSED** — démontré pour les deux modes de découpage |
| Révocation individuelle de credential et propagation au cache Gateway (A-03) | **PASSED** — tracé dans `sources_cache/postgres.py` (filtre `revoked_at IS NULL`) et `sources_cache/file.py` (`_valid()`) ; pas de test d'intégration réel (pas de Postgres/NATS réel disponible dans cet environnement) — **vérification par traçage de code, pas par exécution bout-en-bout** |
| Absence de fuite de secret dans la réponse API / les logs (A-03) | **PASSED** — aucune journalisation de jeton trouvée |
| Bornage réel du découpage par blocs, tailles autour de la frontière, erreur en milieu de lot, renvoi complet sans perte ni doublon (A-05) | **PASSED** — voir tests `test_publisher.py` ci-dessus |
| La documentation ne prétend pas garantir une atomicité broker inexistante (A-05) | **PASSED** — docstring réécrite |
| `services/ingestion-gateway` — suite complète | **PASSED — 46/46** (34 pré-existants + 12 nouveaux : 2 A-04 dans `test_units.py`, 2 A-01 dans `test_syslog.py`, 1 A-05 dans `test_http.py`, 3 A-05 dans `test_publisher.py`, et redécompte des tests pré-existants déjà comptés) |
| `services/baolsec-api` — suite complète | **32 PASSED, 6 FAILED, 0 BLOCKED** — les 3 nouveaux tests A-03 passent ; les 6 échecs sont le défaut `paginate()` ci-dessous, confirmé pré-existant et hors périmètre |

Commandes : `python3 -m pytest tests/ -q` (ingestion-gateway) ;
`POSTGRES_DSN=postgresql://u:p@localhost/db JWT_SECRET=test-secret OPENSEARCH_URL=http://localhost:9200 python3 -m pytest tests/ -q` (baolsec-api, valeurs factices suffisantes car ces tests simulent le pool DB et ne se connectent jamais réellement).

Environnement de test : dépendances installées via pip (réseau PyPI disponible par le
proxy configuré) — `pytest`, `pytest-asyncio`, `httpx`, `jsonschema`,
`rfc3339-validator`, `python-jose[cryptography]`, `passlib[argon2]`,
`opensearch-py[async]`, `psycopg-pool`, `python-multipart`. Packages du dépôt installés
en mode éditable (`pip install -e ... --no-deps`) : `shared/python-common`,
`services/ingestion-gateway`, `services/baolsec-api`.

## Anomalie `paginate()` — hors périmètre Phase 1, non corrigée (consignée sur demande explicite)

**Cause confirmée, et non une simple hypothèse.** `services/baolsec-api/src/baolsec_api/dependencies.py::paginate()`
utilise `conn.cursor()` nu (sans `row_factory`) et lit `row[0]` — correct en production,
car `database.py` configure le pool avec `kwargs={"autocommit": True, "row_factory": None}`
(lignes sous forme de tuples par défaut). Le défaut est **uniquement dans le montage de
test** : `tests/test_routes.py::make_fake_pool()` retourne toujours des lignes en forme
de dict, quel que soit le `row_factory` réellement demandé par le code appelant ; quand
`paginate()` (qui n'en demande aucun) reçoit un dict au lieu d'un tuple, `row[0]` lève
`KeyError: 0`.

- **Confirmé non lié à cette phase** : `dependencies.py`, `routers/users.py` et
  `routers/rules.py` n'ont été modifiés par aucune des corrections A-01/A-03/A-05
  (vérifié par `md5sum` contre la base saine).
- **6 tests concernés** (échouent avant comme après les corrections de cette phase) :
  `tests/test_rbac.py::TestSourcesRBAC::test_get_allowed`,
  `tests/test_rbac.py::TestRulesRBAC::test_get_allowed`,
  `tests/test_rbac.py::TestUsersRBAC::test_list_only_admin`,
  `tests/test_routes.py::TestSources::test_list_sources_analyst`,
  `tests/test_routes.py::TestRules::test_list_rules`,
  `tests/test_routes.py::TestUsers::test_list_users_admin_only`.
- **Non corrigé dans cette phase, sur instruction explicite.** Aucun de ces 6 tests n'a
  été supprimé, désactivé ou modifié pour obtenir une suite artificiellement verte.
- **Proposition de correction future (non appliquée)** : paramétrer le mock de curseur
  de `make_fake_pool()` pour qu'il inspecte le `row_factory` effectivement passé à
  `conn.cursor(...)` et retourne des lignes en tuple (valeurs dans l'ordre des colonnes)
  quand aucun `row_factory` n'est demandé (ou `None`), et des lignes en dict uniquement
  quand `row_factory=dict_row` est explicitement demandé — pour que le mock reflète le
  comportement réel de psycopg plutôt qu'un format figé.

## Fichiers modifiés ou créés (Phase 1, à jour après re-vérification)

| Fichier | Nature |
|---|---|
| `services/ingestion-gateway/src/gateway/syslog/__init__.py` | Modifié — A-01 (+ correction métadonnées DLQ) |
| `services/ingestion-gateway/src/gateway/publisher/__init__.py` | Modifié — A-05 (+ correction docstring atomicité) |
| `services/baolsec-api/src/baolsec_api/routers/sources.py` | Modifié — A-03 |
| `services/ingestion-gateway/tests/test_units.py` | Modifié — tests A-04 |
| `services/ingestion-gateway/tests/test_syslog.py` | Modifié — tests A-01 (2 tests, comptage d'octets ajouté en re-vérification) |
| `services/ingestion-gateway/tests/test_http.py` | Modifié — test A-05 (rejets corrigés en re-vérification) |
| `services/ingestion-gateway/tests/test_publisher.py` | **Créé en re-vérification** — 3 tests A-05 (frontières de bloc, erreur en milieu de lot, renvoi sans perte ni doublon) |
| `services/baolsec-api/tests/test_routes.py` | Modifié — tests A-03 |
| `docs/conception/C26_event_id_limite_json.md` | Créé — décision et vérification A-04 |
| `docs/conception/C26_audit_C6C7_phase1_corrections.md` | Créé puis mis à jour — ce document |

Aucun autre fichier de production ou de test n'a été modifié dans cette phase (vérifié
par comparaison exhaustive contre la base saine extraite de l'archive).

## Points non traités dans cette phase (hors périmètre Phase 1)

- Anomalie `paginate()` (6 tests `baolsec-api` en échec) — cause confirmée, non corrigée
  sur instruction explicite, voir section dédiée ci-dessus.
- A-06 à A-15 : non abordés (Phase 2 à 6 du plan de correction).
- Statut Linux journald pour A-04 : non vérifiable sans exécution réelle de Fluent Bit.
- Vérification du comportement d'authentification après révocation (A-03) et de la
  cohérence du cache Gateway : faite par traçage de code, pas par un test d'intégration
  réel (absence de Postgres/NATS réel dans cet environnement) — limite de validation à
  connaître.

## Limites de validation à connaître

- Aucun test d'intégration réel (Postgres, NATS JetStream) n'a été exécuté dans cet
  environnement : toutes les vérifications reposent sur des tests unitaires avec
  doubles de test (brokers en mémoire, pools simulés) et, pour A-03, sur un traçage de
  code à travers les deux implémentations du registre de sources.
- La suite `baolsec-api` compte 0 test BLOCKED (tous les tests s'exécutent, aucun n'est
  resté inatteignable faute de dépendance) ; les 6 échecs sont des FAILED confirmés, pas
  des BLOCKED.

## Validation requise

La Phase 1 a été validée conditionnellement par l'utilisateur (orientations A-01/A-03/A-05,
classifications A-02/A-04), puis la re-vérification demandée ci-dessus a été exécutée et
son bilan présenté. L'utilisateur a ensuite demandé de poursuivre l'ensemble des phases
restantes (A-06 à A-15) sans attendre une validation intermédiaire par constat, l'archive
complète n'étant générée qu'une fois toutes les phases terminées. Voir
`C26_A06_revocation_cache.md`, `C26_A09_A10_validation.md`,
`C26_A07_A08_A11_collecte_buffering.md`, `C26_A13_A14_parcours_sources.md` et
`C26_A15_confidentialite.md` pour l'état de chacun des constats restants (A-06 à A-15).
Phase 1 (A-01 à A-05) : **close**.

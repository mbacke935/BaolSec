# C26-PRE — préparation de l'environnement d'intégration

## 1. Résumé exécutif

**Statut : PARTIELLEMENT PRÊT.** L'audit a reconstitué la topologie, observé Docker
sans le modifier et préparé une variante Compose isolée validée statiquement. Aucun
conteneur C26, test d'intégration ou test de résilience n'a été exécuté.

Le démarrage n'est pas prudent sur cet hôte : 1,7 à 1,9 Gio de RAM étaient disponibles
et 3,8 à 3,9 Gio des 4 Gio de swap étaient déjà utilisés. Les certificats, sources et règles
C26 dédiés restent également à préparer.

Les mentions sont strictes : **constaté** = observé ; **vérifié statiquement** = lu
ou validé sans démarrage ; **préparé** = ajouté par C26-PRE ; **non vérifié** = sans
preuve d'exécution ; **bloqué** = condition empêchant une validation fiable.

## 2. État Git initial et final

| Élément initial constaté | Valeur |
|---|---|
| Branche | `c25-lab-datasets` |
| Dernier commit | `75a201f test(c25): finalize dataset validation and parser coverage` |
| État | sale avant C26-PRE |
| Anomalie demandée | `services/coverage-worker/src/coverage/repositories/__init__.py` est absent et marqué `D`; son blob suivi est `8b137891…` |

Les changements préexistants (tests API, coverage/indexing, document C26 antérieur,
répertoire C26 non suivi et `.python-version`) ont été préservés. À la fin, les mêmes
modifications suivies sont présentes. `.env` et tous les Compose existants n'ont aucun
diff ; aucun reset, nettoyage, restauration, commit ou push n'a été fait.

## 3. Docker et ressources

La pile active constatée est celle de `infrastructure/compose/compose.yaml`, et non du
Compose racine historique : broker, PostgreSQL, ingestion-gateway,
normalization-worker, detection-worker et incident-builder étaient sains depuis
environ 19 h. `db-migrate` et `broker-init` étaient arrêtés avec code 0. Aucun
conteneur, réseau ou volume C26 n'a été créé ou observé.

| Mesure constatée | Valeur |
|---|---:|
| RAM totale / disponible | 6,5 Gio / 1,7 à 1,9 Gio |
| Swap / utilisé | 4,0 Gio / 3,8 à 3,9 Gio |
| Espace libre | 106 Gio |
| Mémoire des six services BaolSec actifs au relevé | environ 84 Mio |

Ports déjà occupés : `4222`, `5432`, `6514`, `8443`, `8080`, `9090`, `9093` et `443`.
La variante C26 emploie `14222`, `18222`, `15432`, `16514`, `18443`, `18000`, `19090`,
`19200` et `13001` liés à localhost, sans collision évidente.

Ses limites théoriques totalisent 3,44 Gio (dont 1 Gio pour OpenSearch). Ce n'est ni
une réservation ni une garantie : le démarrage complet est bloqué sur cet hôte par la
RAM réellement disponible, le swap saturé et le risque OpenSearch. Le disque n'est pas
le blocage principal.

## 4. Architecture réelle et inventaire

Les Dockerfiles existent pour broker, db-migrate, ingestion-gateway,
normalization-worker, detection-worker, incident-builder, coverage-worker,
indexing-worker et baolsec-api. Leurs `pyproject.toml` et `uv.lock` existent aussi.
L'image OpenSearch n'était pas présente localement : son téléchargement et la
construction des images restent non vérifiés.

Flux vérifiés statiquement dans le code et `infrastructure/broker/topology.json` :

```text
ingestion-gateway -> raw-events / RAW_EVENTS -> normalization-worker
normalization-worker -> normalized-events / NORMALIZED_EVENTS -> detection-worker
                                      |                         -> coverage-worker
                                      +------------------------> indexing-worker
detection-worker -> alerts / ALERTS -> incident-builder -> PostgreSQL
alerts / ALERTS --------------------> indexing-worker -> OpenSearch
```

`indexing-worker` contient les seuls appels d'écriture OpenSearch localisés
(`bulk_index`, `index_one`). L'API ne les appelle pas et utilise OpenSearch pour la
recherche. `incident-builder` écrit `incidents.*` dans PostgreSQL et reçoit les
commandes API par HTTP : PostgreSQL reste la source de vérité des incidents. Cela est
vérifié par lecture, pas en intégration. Le stream `INCIDENTS` attendu par l'indexer
n'est pas créé par la topologie inspectée : ce flux est non vérifié.

## 5. Incohérences découvertes

1. [`compose.yaml`](../../compose.yaml) référence `services/gateway/Dockerfile`,
   `normalizer`, `enricher` et `rule-engine`, absents ; les chemins réels sont
   `ingestion-gateway`, `normalization-worker` et `detection-worker`.
2. `infrastructure/compose/compose.dev.yaml` et `compose.test.yaml` définissent
   seulement `services: {}` : aucune topologie C26.
3. Le fichier C26 préexistant
   [`infrastructure/compose/c26-pre/compose.yaml`](../../infrastructure/compose/c26-pre/compose.yaml)
   échoue à `docker compose config -q`, ligne 31 : URL NATS non quotée dans une
   mapping YAML compacte. Il a été préservé intact.
4. Ce même fichier ne monte pas le certificat, la clé et l'AC exigés par
   `services/ingestion-gateway/src/gateway/config.py`.
5. `topology.json` déclare `coverage-raw`, `coverage-normalized` et `indexing-events`,
   tandis que le code définit `coverage-worker-raw`, `coverage-worker-norm` et
   `indexing-normalized`. La compatibilité des durables est non vérifiée.
6. Les migrations ne chargent ni sources ni règles. `seed_dev.py` et `load_rules.py`
   existent, mais ne sont pas copiés dans `infrastructure/database/Dockerfile`.

## 6. Configuration isolée préparée

`compose.prepared.yaml` sépare projet (`baolsec-c26`), conteneurs, réseau
`baolsec-c26-internal` et cinq volumes `baolsec-c26-*`. Les ports sont localhost et
distincts. Healthchecks et conditions de réussite de `broker-init` et `db-migrate`
protègent le démarrage futur ; Prometheus/Grafana restent dans le profil
`observability`.

Il faudra fournir un fichier local de variables, un répertoire TLS C26 distinct
(`gateway.crt`, `gateway.key`, `sources-ca.crt`) et un jeu dédié de sources/règles.
Aucune valeur ni donnée de la pile active ne doit être réutilisée.

## 7. Contrôles effectués

| Commande / contrôle | Résultat |
|---|---|
| `git branch`, `git log`, `git status` | état initial et final relevé |
| `free -h`, `df -h .`, `ss -ltn` | ressources et ports constatés |
| `docker ps/images/network/volume/stats` | observation non destructive |
| lecture Compose, Dockerfiles, NATS et code | chemins/dépendances vérifiés |
| `docker compose ... compose.yaml config -q` | échec préexistant documenté |
| `docker compose ... compose.prepared.yaml --profile observability config -q` | succès : 14 services, 5 volumes, aucun démarrage |
| analyse PyYAML de `prometheus.prepared.yml` | succès |
| `git diff --check` | succès |

## 8. Fichiers préparés

| Fichier | Rôle |
|---|---|
| `infrastructure/compose/c26-pre/compose.prepared.yaml` | pile C26 isolée, statiquement valide |
| `infrastructure/compose/c26-pre/.env.prepared.example` | variables et placeholders sans secret |
| `infrastructure/compose/c26-pre/prometheus.prepared.yml` | cibles de métriques C26 |
| `docs/conception/C26_PRE_preparation_environnement.md` | rapport C26-PRE |

## 9. Risques résiduels et décision

Non vérifiés : build/images, téléchargement OpenSearch, santé réelle, TLS,
migrations, JetStream, durables, chargement de données C26, API, indexation,
persistance et supervision. Une validation Compose ne construit ni ne démarre rien.

**Décision : PARTIELLEMENT PRÊT.** Une machine dédiée avec au moins **8 Gio réellement
libres** doit être préparée ; c'est la prochaine étape technique prioritaire avant de
demander l'autorisation explicite de démarrer `compose.prepared.yaml`.

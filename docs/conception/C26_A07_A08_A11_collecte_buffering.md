# C26 — A-07, A-08, A-11 : limite UDP pfSense, objectif 72h, statut des tests réels

Date : 24 novembre 2026.

## A-07 et A-11 — déjà correctement documentés dans C7 : classification de l'audit corrigée

Vérification faite contre `docs/conception/C7_Agents_et_collecte_BaolSec.docx` (le document
de conception réel, pas seulement le code et les README) :

- La limite UDP pfSense est déjà documentée explicitement dans C7 (section 4 et section 5,
  tableau « Chaîne de conservation ») : *« pfSense → collecteur : Aucun : UDP sur le réseau
  local — Aucune [confirmation] : seul maillon non protégé, réduit au réseau local »*. C7
  explique aussi pourquoi (un relais rsyslog TCP sans accusé applicatif avait été essayé et
  perdait des messages ; remplacé par le collecteur Fluent Bit actuel) et propose déjà
  syslog-ng sur pfSense si TCP devient nécessaire.
- Le statut « non testé réellement » de Windows et pfSense est déjà consigné explicitement
  dans le tableau C7 « Points non résolus » : *« Windows non testé avec un agent réel »*,
  *« pfSense réel non testé »*, avec renvoi vers C27 pour ces tests.
- `agents/README.md` reprend la même information (tableau « Chaîne de conservation »).
- Configuration socket/buffer déjà en place côté collecteur
  (`agents/fluent-bit/syslog-collector/fluent-bit.yaml`) : `receive_buffer_size: 4M`,
  `buffer_chunk_size`/`buffer_max_size: 64k`, tampon disque (`storage.type: filesystem`).

**Correction du rapport d'audit** : A-07 et A-11 ne constituent pas des lacunes de
documentation — C7 documente déjà, avec précision, la limite intrinsèque et son statut de
test. Ce qui reste réellement non fait, et que C7 reconnaît lui-même comme tel, c'est le
test de perte sous charge réelle (A-07) et les tests réels Windows/pfSense (A-11) : ce sont
des tests d'intégration sur matériel/réseau réel, renvoyés à C27 par le document de
conception lui-même, et non réalisables dans cet environnement de travail (pas
d'équipement pfSense réel, pas de machine Windows, pas de réseau à charger). Aucune
correction de code ou de documentation n'était donc nécessaire pour A-07/A-11 au-delà de
cette vérification — ce qui a été fait est une vérification de cohérence, pas une
correction.

## A-08 — objectif 72h : déjà bien dimensionné dans C7, mais deux défauts d'observabilité réels trouvés et corrigés

Le dimensionnement par profil, la formule de calcul du tampon, le comportement de
suppression des plus anciens morceaux en saturation, et le renvoi vers C27 pour la mesure
réelle des débits sont déjà présents dans C7 (section 6) et dans `agents/README.md`
(section « Objectif de conservation : 72 heures »). Pas de changement nécessaire sur ce
point : l'audit demandait aussi des « alertes buffer », et c'est en vérifiant la chaîne
d'observabilité nécessaire à une telle alerte que deux défauts réels, non liés à cette
demande initiale mais la rendant actuellement impossible à satisfaire, ont été trouvés.

### Défaut 1 — Prometheus ne scrutait jamais réellement la Gateway ni le Normalization Worker

`docker/prometheus/prometheus.yml` (monté par `compose.yaml` pour le service `prometheus`)
ciblait :

- `gateway:9100` — mais le service compose s'appelle `ingestion-gateway`, pas `gateway` ;
  et son port réel (`gateway/config.py::metrics_port = 9000`, confirmé aussi par le
  healthcheck compose qui interroge `localhost:9000/health`) n'est pas 9100.
- `normalizer:9101` — même défaut de nom d'hôte (le service s'appelle
  `normalization-worker`).

Sur le réseau Docker de `compose.yaml`, un nom d'hôte inconnu ne résout tout simplement
pas : ces deux cibles n'étaient **jamais** scrutées avec succès. La Gateway — pourtant le
sujet même de cet audit — n'avait donc aucune métrique réellement collectée par
Prometheus, malgré son `/metrics` effectivement exposé et fonctionnel.

**Correction** : noms d'hôte et port corrigés dans `docker/prometheus/prometheus.yml`
(`ingestion-gateway:9000`, `normalization-worker:9101`).

### Défaut 2 — la variable d'environnement du port de métriques était silencieusement ignorée pour deux services

`normalization-worker` et `incident-builder` utilisent `pydantic_settings` avec un
`env_prefix` propre (`NORMALIZER_`, `INCIDENTS_`). `compose.yaml` leur passait pourtant la
variable **sans** ce préfixe (`METRICS_PORT: "9101"` / `"9104"`), qui ne correspond à
aucun champ de leur `Settings` — elle était donc silencieusement ignorée par
`pydantic-settings` (`extra="ignore"`), et chacun de ces deux services écoutait en réalité
sur son port **par défaut** (9000), pas sur le port que Prometheus croyait scruter. Même
après la correction du Défaut 1, `normalization-worker:9101` serait donc resté injoignable.

Pas un défaut systémique : vérifié aussi pour `coverage-worker` (préfixe `COVERAGE_`,
variable déjà nommée `COVERAGE_METRICS_PORT` — correct) et `indexing-worker`/`baolsec-api`
(pas de préfixe dans leur `Settings` — `METRICS_PORT` nu les atteint correctement). `enricher`
et `rule-engine`/`detection-worker` sont marqués `profiles: ["todo"]` (non encore
implémentés) : non concernés pour l'instant.

**Correction** : `compose.yaml` renommé en `NORMALIZER_METRICS_PORT` et
`INCIDENTS_METRICS_PORT` pour ces deux services, afin que la valeur explicitement prévue
(9101, 9104) prenne réellement effet et corresponde à ce que Prometheus scrute.

### Non fait, sciemment, et pourquoi

- **Aucune règle d'alerte Prometheus sur la taille du tampon n'a été ajoutée.** Le tampon
  de 72h est un tampon **disque, local à chaque agent Fluent Bit**, sur des machines tierces
  (serveurs Linux, postes Windows, collecteur pfSense) qui ne sont pas des services du
  `compose.yaml` et ne sont donc pas atteignables par le Prometheus central de BaolSec sans
  exportateur dédié sur chacune de ces machines (ex. `node_exporter` + un *textfile
  collector* mesurant `$BAOLSEC_STATE_DIR`, ou l'activation du module de monitoring HTTP de
  Fluent Bit lui-même). Ajouter une règle d'alerte sur une métrique qui n'existe nulle part
  dans ce Prometheus aurait été une fonctionnalité fictive (explicitement proscrite par le
  référentiel architectural : *« Créer des fonctionnalités fictives »*). C'est une décision
  d'exploitation (quel mécanisme de supervision déployer sur des machines tierces) qui
  dépasse le périmètre de cette correction et mérite d'être tranchée séparément plutôt que
  décidée unilatéralement ici.
- **`postgres-exporter:9187`**, autre cible de `prometheus.yml`, ne correspond à aucun
  service du `compose.yaml` (aucun service `postgres-exporter` n'y existe). C'est un défaut
  réel, mais sans rapport avec C6/C7/A-08 : non corrigé ici, pour ne pas sortir du
  périmètre de cette phase ; à consigner séparément.

### Vérification effectuée

- `docker/prometheus/prometheus.yml` et `compose.yaml` : syntaxe YAML valide après édition
  (`yaml.safe_load`), vérifiée.
- Noms de service et ports confirmés par lecture directe de `compose.yaml` et des fichiers
  `config.py`/`main.py` de chaque service concerné (pas une supposition).
- **Non exécuté** : aucun test d'intégration réel (pas de démon Docker actif dans cet
  environnement — cf. A-09/A-10). Le scrape Prometheus effectif sur la stack complète
  n'a donc pas pu être observé en direct ; la correction est une correction de
  configuration statique, vérifiée par lecture croisée des noms/ports réels, pas par une
  exécution bout en bout.

## Fichiers modifiés pour A-08

| Fichier | Nature |
|---|---|
| `docker/prometheus/prometheus.yml` | Corrigé — cibles gateway/normalizer (nom d'hôte + port) |
| `compose.yaml` | Corrigé — `NORMALIZER_METRICS_PORT`, `INCIDENTS_METRICS_PORT` |

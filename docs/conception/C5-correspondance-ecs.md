# C5 — Table de correspondance C4 → ECS 9.5.0 → sources

Ce document applique l'ADR 0001 (`docs/decisions/0001-schema-commun-ecs.md`). Il fixe, champ par champ, comment chaque information du modèle C4 est représentée en ECS 9.5.0 et d'où elle vient pour chacune des quatre sources du prototype. Il sert de base aux JSON Schemas de `shared/contracts/` et au code de `normalization-worker`.

**Conventions**
- *absent* : la source ne fournit pas cette information ; le champ est omis, aucune valeur n'est inventée.
- *n/a* : le champ n'a pas de sens pour ce type d'événement.
- Les valeurs génériques (`-`, `anonymous`, `N/A`) sont omises.
- Les noms de champs des sources sont ceux des formats d'origine : auth.log/journald (Linux), journal Sécurité (Windows), `filterlog` (pfSense), cible `LOG` du noyau (iptables), format « combined » (serveur web), journaux JSON (application).

---

## 1. Champs communs : C4 → ECS

| Champ C4 | Champ normalisé | Type | Renseigné par | Remarque |
|---|---|---|---|---|
| event_id | `event.id` | keyword | ingestion-gateway | Identifiant natif fiable (Windows : `win:<Computer>:<Channel>:<EventRecordID>`) ou empreinte SHA-256 de (source, format, contenu brut) (C3 3.1). Conservé tel quel dans toute la chaîne ; `_id` OpenSearch. |
| source_id | `baolsec.source.id` | keyword (uuid) | ingestion-gateway | Source authentifiée (config.sources). |
| source_type | `baolsec.source.type` | keyword | ingestion-gateway | `linux`, `windows`, `firewall`, `http`. |
| — (nom de la source) | `baolsec.source.name` | keyword | normalization-worker (enrichissement) | Copié depuis config.sources. |
| — (criticité de l'actif) | `baolsec.source.criticality` | keyword | normalization-worker (enrichissement) | `faible`, `moyenne`, `elevee`, `critique` ; copiée depuis config.sources si l'Administrateur l'a renseignée. Distincte de la sévérité de l'événement. |
| timestamp / original_ts | `@timestamp` | date | normalization-worker | Heure d'origine ; à défaut, heure de réception (voir `baolsec.timestamp_source`). |
| — | `baolsec.timestamp_source` | keyword | normalization-worker | `original` ou `received`. |
| received_at | `baolsec.received_at` | date | ingestion-gateway | Heure de réception à la passerelle. |
| — (lecture par l'agent) | `event.created` | date | agent, si fourni | Absent pour Syslog direct. |
| — (indexation) | `event.ingested` | date | pipeline d'ingestion OpenSearch | Heure de l'écriture réussie (ADR 0001, règle 3). |
| category | `event.category` (+ `event.type`) | keyword (tableaux) | normalization-worker | Valeurs autorisées ECS uniquement (section 3). |
| action | `event.action` | keyword | normalization-worker | Vocabulaire BaolSec (section 3). |
| outcome | `event.outcome` | keyword | normalization-worker | `success`, `failure`, `unknown`. |
| severity | `event.severity` / `log.syslog.severity.code` / `log.level` | long / long / keyword | normalization-worker | Sévérité **native** (section 4). |
| — | `baolsec.severity.label` | keyword | normalization-worker | `info`, `faible`, `moyenne`, `elevee`, `critique`. |
| — | `baolsec.severity.score` | byte | normalization-worker | 0 (info) à 4 (critique). |
| user_name | `user.name` | keyword | normalization-worker | Compte concerné par l'événement (section 2). Renseigné dès que la source fournit une identité ; absent sinon, sans rendre l'événement invalide. |
| host_name | `host.name` | keyword | normalization-worker | Machine où l'événement a été enregistré. Pour un pare-feu : `observer.name`. |
| src_ip | `source.ip` | ip | normalization-worker | |
| — | `source.port` | long | normalization-worker | Si fourni. |
| dst_ip | `destination.ip` | ip | normalization-worker | Si fourni. |
| — | `destination.port` | long | normalization-worker | Si fourni. |
| message | `message` | text | normalization-worker | Texte lisible. |
| raw | `event.original` | keyword (non indexé) | normalization-worker | Copie exacte de l'événement brut. |
| enrichment (classification IP) | `baolsec.ip_scope.source`, `baolsec.ip_scope.destination` | keyword | normalization-worker | `private` ou `public`, pour `source.ip` et `destination.ip`. |
| — | `related.ip`, `related.user`, `related.hosts` | keyword (tableaux) | normalization-worker | Toutes les IP, comptes et hôtes de l'événement, pour la recherche. |
| schema_version | `ecs.version` | keyword | normalization-worker | `9.5.0`. |
| — | `baolsec.contract` | keyword | normalization-worker | `normalized_event/v1`. |
| — (origine technique) | `event.provider`, `event.dataset`, `event.module` | keyword | normalization-worker | Voir section 2. |
| — (code natif) | `event.code` | keyword | normalization-worker | Identifiant d'événement de la source (ex. Windows 4625). |

---

## 2. Correspondance par source

| Champ normalisé | Linux (auth.log, journald) | Windows (journal Sécurité) | Pare-feu (pfSense `filterlog` / iptables `LOG`) | Application web (format combined / JSON applicatif) |
|---|---|---|---|---|
| `@timestamp` | Horodatage Syslog ou `__REALTIME_TIMESTAMP` journald | `TimeCreated` | Horodatage Syslog (pfSense) ; horodatage du journal noyau (iptables) | `$time_local` ; champ horaire du JSON |
| `event.code` | absent | `EventID` (4624, 4625, 4688…) | absent | absent |
| `event.provider` | nom du programme (`sshd`, `sudo`) | `Microsoft-Windows-Security-Auditing` | `filterlog` (pfSense) ; `kernel` (iptables) | nom du serveur web ou de l'application |
| `event.dataset` | `linux.auth` | `windows.security` | `pfsense.filterlog` ; `iptables.log` | `web.access` ; `app.log` |
| `user.name` | Compte cité (`Failed password for admin`) | `TargetUserName` (4624, 4625) ; `SubjectUserName` (4688) | absent | `$remote_user` (si authentifié) ; champ utilisateur du JSON |
| `host.name` | `HOSTNAME` Syslog / `_HOSTNAME` journald | `Computer` | n/a (voir `observer.name`) | Nom du serveur (configuration de l'agent) |
| `observer.name` / `.vendor` / `.product` / `.type` | n/a | n/a | Nom du pare-feu ; `Netgate` / `pfSense` / `firewall` (pfSense) ; nom de la machine / — / `iptables` / `firewall` (iptables) | n/a |
| `source.ip` | Adresse après `from` | `IpAddress` (4624, 4625) ; absent (4688) | Adresse source (`filterlog`) ; `SRC=` (iptables) | `$remote_addr` ; champ IP client du JSON |
| `source.port` | Port après `port` | `IpPort` | Port source ; `SPT=` | absent |
| `destination.ip` | absent | absent | Adresse destination ; `DST=` | absent |
| `destination.port` | absent | absent | Port destination ; `DPT=` | absent |
| `network.transport` | n/a | n/a | Protocole (`tcp`, `udp`, `icmp`) ; `PROTO=` | n/a |
| `network.direction` | n/a | n/a | `in` → `ingress`, `out` → `egress` (pfSense) ; interface `IN=`/`OUT=` (iptables) | n/a |
| `rule.id` | n/a | n/a | Numéro de règle du pare-feu (pfSense) ; préfixe `LOG` configuré (iptables) | n/a |
| `process.name` / `process.pid` | Programme et PID Syslog (`sshd[1842]`) | — / `NewProcessId` (4688) | n/a | absent |
| `process.executable` | absent | `NewProcessName` (4688) | n/a | absent |
| `process.command_line` | absent (sauf sudo : `COMMAND=`) | `CommandLine` (4688, si l'audit de ligne de commande est activé) | n/a | absent |
| `http.request.method` | n/a | n/a | n/a | Méthode de `$request` |
| `url.original` | n/a | n/a | n/a | Chemin de `$request` |
| `http.response.status_code` | n/a | n/a | n/a | `$status` |
| `user_agent.original` | n/a | n/a | n/a | `$http_user_agent` |
| `baolsec.windows.logon_type` | n/a | `LogonType` (4624, 4625) | n/a | n/a |
| Sévérité native | `log.syslog.severity.code` (journald `PRIORITY`) | absent (niveau « Information » non significatif pour l'audit) | `log.syslog.severity.code` | `log.level` (JSON) ; absent (format combined) |
| `event.original` | Ligne complète | Événement XML ou JSON exporté par l'agent | Ligne complète | Ligne complète / objet JSON |

---

## 3. Catégorisation : `event.category`, `event.type`, `event.action`, `event.outcome`

Les catégories et types sont pris dans les listes autorisées d'ECS. `event.action` est un vocabulaire BaolSec, stable, utilisé par les règles.

| Source | Événement d'origine | `event.category` | `event.type` | `event.action` | `event.outcome` |
|---|---|---|---|---|---|
| Linux | `Failed password for … from …` (sshd) | `authentication` | `start` | `ssh_login` | `failure` |
| Linux | `Accepted password/publickey for …` (sshd) | `authentication` | `start` | `ssh_login` | `success` |
| Linux | `Invalid user … from …` (sshd) | `authentication` | `start` | `ssh_login` | `failure` |
| Linux | `sudo: … COMMAND=…` | `process` | `start` | `sudo_command` | `success` |
| Linux | `authentication failure` (sudo / PAM) | `authentication` | `start` | `sudo_auth` | `failure` |
| Windows | 4624 — ouverture de session réussie | `authentication` | `start` | `logon` | `success` |
| Windows | 4625 — échec d'ouverture de session | `authentication` | `start` | `logon` | `failure` |
| Windows | 4634 — fermeture de session | `authentication` | `end` | `logoff` | `success` |
| Windows | 4688 — création de processus | `process` | `start` | `process_start` | `success` |
| Pare-feu | Paquet autorisé (`pass` / préfixe d'acceptation) | `network` | `connection`, `allowed` | `connection_allowed` | `unknown` |
| Pare-feu | Paquet bloqué (`block` / préfixe de rejet) | `network` | `connection`, `denied` | `connection_denied` | `unknown` |
| Web | Requête avec statut < 400 | `web` | `access` | `http_request` | `success` |
| Web | Requête avec statut ≥ 400 | `web` | `access`, `error` | `http_request` | `failure` |
| Application | Connexion à l'API (JSON) | `authentication` | `start` | `api_login` | `success` ou `failure` selon le JSON |

**Remarque sur le pare-feu.** La décision du pare-feu est portée par `event.type` (`allowed` / `denied`) et `event.action`. `event.outcome` vaut `unknown`, car un blocage est un succès du pare-feu mais un échec de la connexion : utiliser `failure` ou `success` serait ambigu pour les règles.

Un événement que le parseur reconnaît mais qui n'est pas dans cette table reçoit `event.category` selon la source, `event.type: info` et `event.action` dérivé du programme ; un événement que le parseur ne sait pas lire part en file de rejet (C3 W2).

---

## 4. Sévérité : native, normalisée, score

| Source | Sévérité native conservée | Règle de conversion vers `baolsec.severity.label` (score) |
|---|---|---|
| Linux | `log.syslog.severity.code` (0 à 7) | 0–2 → `critique` (4) ; 3 → `elevee` (3) ; 4 → `moyenne` (2) ; 5 → `faible` (1) ; 6–7 → `info` (0) |
| Windows | absente | Selon l'événement : 4625 → `faible` (1) ; 4624, 4634, 4688 → `info` (0) |
| Pare-feu | `log.syslog.severity.code` si présent | Selon la décision : `connection_denied` → `faible` (1) ; `connection_allowed` → `info` (0). La sévérité Syslog n'est pas utilisée, car elle décrit le message et non le risque. |
| Web | `log.level` (JSON) ; absente (combined) | Statut 5xx → `moyenne` (2) ; 4xx → `faible` (1) ; autres → `info` (0) ; pour le JSON : `ERROR` → `moyenne`, `WARN` → `faible`, autres → `info` |

- `event.severity` n'est renseigné que si une source fournit une échelle numérique propre ; aucune des quatre sources du prototype ne le fait, il reste donc absent. La valeur native Syslog est rangée dans `log.syslog.severity.code`, comme ECS le prévoit.
- Ces conversions sont des **valeurs proposées**, paramétrables, et seront ajustées après les tests (C24 à C28).
- La sévérité d'une **alerte** ne vient pas de l'événement : elle est fixée par la règle de détection (section 6).

---

## 5. Champs `baolsec.*`

| Champ | Type | Description |
|---|---|---|
| `baolsec.contract` | keyword | Version du contrat (`normalized_event/v1`, `alert/v1`). |
| `baolsec.source.id` | keyword | Identifiant de la source dans config.sources. |
| `baolsec.source.type` | keyword | `linux`, `windows`, `firewall`, `http`. |
| `baolsec.source.name` | keyword | Nom de la source. |
| `baolsec.source.ingestion_mode` | keyword | `direct` ou `rejeu`. |
| `baolsec.source.criticality` | keyword | Criticité de l'actif : `faible`, `moyenne`, `elevee`, `critique` (facultatif). |
| `baolsec.received_at` | date | Réception par la passerelle. |
| `baolsec.timestamp_source` | keyword | `original` ou `received`. |
| `baolsec.severity.label` | keyword | Sévérité normalisée. |
| `baolsec.severity.score` | byte | 0 à 4. |
| `baolsec.ip_scope.source` | keyword | `private` ou `public` pour `source.ip` (à ne pas confondre avec `baolsec.source`, la source de journaux). |
| `baolsec.ip_scope.destination` | keyword | `private` ou `public` pour `destination.ip`. |
| `baolsec.windows.logon_type` | keyword | Type d'ouverture de session Windows (aucun champ ECS équivalent). |
| `baolsec.alert.window_start` | date | Début de la fenêtre de la règle (alertes). |
| `baolsec.alert.event_ids` | keyword (tableau) | Événements justificatifs (alertes). |

---

## 6. Alertes (`alert/v1`)

| Champ C4 | Champ normalisé | Remarque |
|---|---|---|
| alert_id | `event.id` | Identifiant déterministe ; `_id` OpenSearch. |
| — | `event.kind` | `alert`. |
| rule_id / rule_name | `rule.id`, `rule.name`, `rule.version` | Règle de détection BaolSec (config.rules). |
| severity | `baolsec.severity.label`, `baolsec.severity.score` | Fixée par la règle. |
| triggered_at | `@timestamp` | Heure de déclenchement. |
| window_start | `baolsec.alert.window_start` | |
| entities | `user.name`, `source.ip`, `host.name` (+ `related.*`) | Entités utilisées par la corrélation (C3 3.8). |
| event_ids | `baolsec.alert.event_ids` | Références vers les événements justificatifs. |
| catégorie | `event.category` | Catégorie des événements déclencheurs (sert aux enchaînements de la règle R4). |
| — | `ecs.version`, `baolsec.contract`, `event.ingested` | Comme pour les événements. |

Dans un **événement** de pare-feu, `rule.id` désigne la règle du pare-feu ; dans une **alerte**, il désigne la règle de détection BaolSec. Les deux vivent dans des index distincts (`events-*`, `alerts-*`) et ne se confondent pas.

---

## 7. Décisions validées

1. Vocabulaire `event.action` de la section 3 ; pour le pare-feu, `event.outcome: unknown` et décision portée par `event.type`.
2. Conversions de sévérité de la section 4 (valeurs de départ, ajustables après les tests).
3. Pare-feu décrit par `observer.*` et non `host.name` ; pour la corrélation (C3 3.8), l'entité « hôte » d'une alerte réseau est `destination.ip`.
4. `event.ingested` posé par un pipeline d'ingestion OpenSearch.
5. Champs de C4 (index `events-*` et `alerts-*`, C4 section 6) renommés selon cette table.

Les contrats correspondants sont dans `shared/contracts/` ; `scripts/testing/validate_contracts.py` vérifie que les exemples par source sont acceptés et que les exemples invalides sont rejetés.

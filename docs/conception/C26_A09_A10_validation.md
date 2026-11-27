# C26 — A-09 et A-10 : validations Fluent Bit et tests Gateway

Date : 24 novembre 2026. Aucune ligne de production modifiée pour ces deux points :
A-09 reste un blocage d'environnement, A-10 est maintenant résolu (tests exécutables).

## A-10 — Tests Gateway non exécutables (VALIDATION BLOQUÉE selon l'audit) : **résolu**

L'audit constatait que les `.venv` fournis dans l'archive n'étaient pas
fonctionnels dans son environnement (pytest absent/mauvais shebang, dépendances
`nats`/`psycopg` absentes du Python système), empêchant toute exécution.

Dans le présent environnement de travail, un environnement pytest fonctionnel a été
reconstruit (voir aussi `C26_audit_C6C7_phase1_corrections.md`) :

- Python système 3.13, `pytest` 9.1.1 installés.
- Packages du dépôt installés en mode éditable, sans leurs dépendances propres
  (`pip install -e ... --no-deps`) : `shared/python-common`,
  `services/ingestion-gateway`, `services/baolsec-api`.
- Dépendances tierces manquantes installées depuis PyPI (réseau disponible via le
  proxy configuré de cet environnement) : `pytest-asyncio`, `httpx`, `jsonschema`,
  `rfc3339-validator`, `python-jose[cryptography]==3.5.0`, `passlib[argon2]==1.7.4`,
  `opensearch-py[async]==2.8.0`, `psycopg-pool==3.3.3`, `python-multipart==0.0.9`.
- Variables d'environnement factices suffisantes pour `baolsec-api` (ces tests
  simulent le pool DB et ne se connectent jamais réellement) :
  `POSTGRES_DSN`, `JWT_SECRET`, `OPENSEARCH_URL`.

**Résultat, re-confirmé dans ce tour (24/11/2026) :**

| Suite | Résultat |
|---|---|
| `services/ingestion-gateway` (`python3 -m pytest tests/ -q`) | **48/48 PASSED** (46 après Phase 1 + 2 nouveaux tests A-06) |
| `services/baolsec-api` | **32 PASSED, 6 FAILED** (défaut `paginate()` pré-existant, hors périmètre, documenté séparément) |

**Limite de cette résolution — à ne pas surinterpréter :** ceci lève le blocage
*d'exécution des tests unitaires Python*. Cela ne constitue **pas** une validation des
tests d'intégration réels contre Postgres/NATS/OpenSearch réels (aucun de ces services
n'est démarré dans cet environnement), ni des tests Docker Compose
(`tests/integration/gateway`, `tests/integration/agents`). Ces derniers restent non
exécutés ici.

## A-09 — Validation réelle des configurations Fluent Bit : **toujours bloquée**

La cible `make agents-check` lance, pour chaque configuration (`linux/fluent-bit.yaml`,
`linux/fluent-bit-journald.yaml`, `webapp/fluent-bit.yaml`,
`syslog-collector/fluent-bit.yaml`, `test/fluent-bit-test.yaml`) :

```
docker run --rm ... fluent/fluent-bit:5.1.5 --dry-run -c /agents/<config>
```

**Vérifié, pas supposé :** cet environnement n'a pas de démon Docker actif
(`docker info` échoue : *« failed to connect to the docker API at
unix:///var/run/docker.sock ... no such file or directory »*), et le binaire
`fluent-bit` n'est pas installable via le gestionnaire de paquets système disponible
ici (`apt-get install fluent-bit` : paquet introuvable). `make agents-check` ne peut
donc **pas** être exécuté dans cet environnement — comme dans l'environnement d'audit
initial. Ce n'est pas un résultat d'échec de validation : c'est un blocage
d'environnement, au même titre que ce que l'audit avait déjà constaté pour A-09/A-10.

**Vérification partielle effectuée, de portée limitée et explicitement non
équivalente au `--dry-run` réel de Fluent Bit :**

- Syntaxe YAML de chacune des 5 configurations : valide (`yaml.safe_load` sans erreur,
  clés de premier niveau `service`/`includes`/`pipeline` présentes dans chacune).
- Résolution des `includes` et `parsers_file` référencés : tous les fichiers cibles
  existent effectivement sur le disque (`agents/fluent-bit/common/gateway-output.yaml`,
  `agents/fluent-bit/syslog-collector/parsers.yaml`).

Cette vérification ne remplace pas `--dry-run` : elle ne valide ni la sémantique des
plugins, ni les options de buffering, ni la compatibilité avec Fluent Bit 5.1.5
spécifiquement, ni le comportement réel des parsers sur des données réelles. Le statut
d'A-09 reste **BLOCKED**, pas PASSED.

La configuration Windows (`winevtlog`) reste, comme le notait déjà l'audit, non
vérifiable autrement que sur un agent Windows réel — hors de portée de cet
environnement Linux, quelle que soit la disponibilité de Docker.

## Recommandation pour une validation réelle

Exécuter `make agents-check` et la suite `test-agents` sur la machine de
développement de l'utilisateur (ou tout environnement disposant d'un démon Docker
actif et d'un accès au registre `docker.io`), puis consigner les résultats réels dans
ce document ou un document dédié. Ceci reste hors périmètre de ce qui peut être fait
dans cet environnement de travail.

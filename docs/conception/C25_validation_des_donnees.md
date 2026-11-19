# C25 — Validation des données publiques et scénarios de détection

## Périmètre et reproductibilité

Le manifeste `test-data/manifest.yaml` est l'inventaire de référence des douze artefacts publics. Il conserve la provenance, la révision, le chemin amont, SHA-256, licence `null` lorsque non vérifiée, et les métadonnées de validation. Les huit entrées directement consommables sont normalisées ; les quatre EVTX ne le sont jamais directement.

Depuis Ubuntu, avec l'environnement du normaliseur :

```bash
cd services/normalization-worker
uv sync --extra dev
uv run --extra dev python ../../scripts/testing/validate_contracts.py
uv run --extra dev pytest -p no:cacheprovider -q -s
```

La conversion reproductible est :

```bash
uv run --with python-evtx==0.8.1 python scripts/testing/evtx_to_fluentbit.py \
  test-data/public/windows/*.evtx > /tmp/windows-security.jsonl
sha256sum /tmp/windows-security.jsonl test-data/public/windows-security.jsonl
```

Le test ne réécrit jamais le JSONL public : il convertit en mémoire/temporaire et compare le résultat au dérivé référencé par le manifeste.

## Garanties et limites

`test_jeux_publics.py` lit exclusivement le manifeste : il vérifie les 12 chemins, SHA-256, provenance, révision, format, topologie EVTX→JSONL et parseur. Il teste ensuite les huit flux directement exploitables, les sorties ECS et les actions attendues. Une ligne normalisée génériquement n'est pas assimilée à une interprétation métier ni à un déclenchement de règle.

Les licences demeurent non vérifiées (`license: null`). Les validations C25 sont locales ; elles ne valident ni NATS, ni OpenSearch, ni Docker, ni la publication réelle en DLQ.

## Matrice des scénarios C26

Tous les scénarios ci-dessous sont **synthétiques déterministes**, sauf indication contraire. Ils ne génèrent aucun trafic externe.

| ID | Objectif / règle | Entrées ordonnées et champs requis | Seuil / fenêtre | Attendu / négatif |
|---|---|---|---|---|
| C25-A1 | Force brute SSH — AUTH-001 | 5 `ssh_login/failure`, même `user.name`, `source.ip`, timestamps croissants | 5 / 10 min | Alerte AUTH-001 ; 4 échecs : aucune alerte |
| C25-A2 | Succès après force brute — AUTH-002 | A1 puis `ssh_login/success`, même groupe | 5 + succès / 10 min | AUTH-002 ; succès hors fenêtre : aucune alerte |
| C25-A3 | Password spraying — AUTH-003 | 4 échecs, même IP, 4 utilisateurs distincts | 4 distincts / 5 min | AUTH-003 ; 4 tentatives sur un seul compte : aucune alerte |
| C25-F1 | Blocages réseau — FW-001 | 20 `connection_denied`, même source | 20 / 5 min | FW-001 ; 19 : aucune alerte |
| C25-F2 | Balayage de ports — FW-002 | 10 refus, même source, 10 `destination.port` distincts | 10 distincts / 2 min | FW-002 ; ports répétés : aucune alerte |
| C25-S1 | PowerShell encodé — SYS-001 | Windows 4688 avec `process.command_line` contenant `powershell -enc` | simple | SYS-001 ; PowerShell sans option encodée : aucune alerte |
| C25-W1 | 401/403 répétés — WEB-001 | 15 réponses HTTP 401 ou 403, même IP | 15 / 5 min | WEB-001 ; 14 : aucune alerte |
| C25-W2 | 404 répétés — WEB-002 | 30 réponses HTTP 404, même IP | 30 / 2 min | WEB-002 ; 29 : aucune alerte |

Les datasets publics servent à valider des formats et l'extraction locale. Aucun dataset public n'est déclaré déclencheur de ces règles sans exécution dédiée de la détection.

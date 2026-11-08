# Normalisation et enrichissement (service 2)

Référence : C3, workflow W2 ; contrats `raw_event/v1` et `normalized_event/v1`, table de
correspondance `docs/conception/C5-correspondance-ecs.md` (C5) ; cartes C9 (normalisation) et
C10 (enrichissement).

Lit les événements bruts de `raw-events`, les convertit en ECS 9.5.0, les enrichit, les contrôle
avec le schéma du contrat, puis les publie dans `normalized-events` avec le même `event_id`.

## Traitement d'un message

1. Lecture par le consommateur durable `normalization` (le même pour toutes les instances).
2. Contrôle du message reçu (`raw_event/v1`).
3. Parseur choisi selon le type de la source authentifiée par la passerelle :

   | Type | Contenu reçu | Parseur |
   |---|---|---|
   | `linux` | ligne d'auth.log (texte) ou enregistrement journald (JSON) | SSH, sudo, échecs PAM ; journal du pare-feu (`IN= OUT= SRC= DST=`) |
   | `windows` | enregistrement winevtlog (JSON, `EventData` nommé) | 4624, 4625, 4634, 4688 |
   | `firewall` | ligne Syslog de pfSense reçue par le collecteur | `filterlog` (IPv4, IPv6, TCP, UDP, ICMP) |
   | `http` | ligne du journal d'accès (combined ou common) ou ligne JSON de l'application | requêtes HTTP, connexions à l'API |

4. Enveloppe commune : `@timestamp`, `event.id`, `event.created`, `event.original`, sévérité normalisée.
5. Enrichissement (C10) : nom et criticité de la source, hôte de repli, classement des adresses IP.
6. Champs `related.ip`, `related.user`, `related.hosts`.
7. Contrôle par le schéma `normalized_event/v1`, publication, attente du PubAck, puis acquittement
   du message brut.

Un événement Linux, Windows ou applicatif reconnu mais absent de la table C5 reste normalisé :
catégorie `host` (ou `web`), type `info`, action dérivée du programme ou de l'identifiant
(`cron`, `windows_4672`…).

## Erreurs

| Cas | Motif (`reason_code`) | Effet |
|---|---|---|
| Message `raw-events` illisible ou non conforme | `validation_error` | file de rejet à la 1re tentative |
| Contenu qu'aucun parseur ne reconnaît | `parse_error` | file de rejet à la 1re tentative |
| Événement produit non conforme au contrat | `mapping_error` | file de rejet à la 1re tentative |
| Broker indisponible à la publication | `processing_error` | nouvelle livraison (5, 15, 30, 60 s), file de rejet à la 5e |

Une nouvelle tentative ne changerait rien aux trois premiers cas : ils partent en file de rejet
immédiatement. Le message brut n'est acquitté qu'après la confirmation de la file de rejet ; si
elle refuse le message, il sera relivré.

Si le référentiel des sources est indisponible depuis plus de 5 minutes, le service suspend la
lecture de `raw-events` (les messages attendent dans le broker) plutôt que de publier des
événements sans enrichissement. `/health` répond alors 503.

## Horodatage

- Horodatage d'origine quand la source le fournit (`baolsec.timestamp_source: original`), sinon
  heure de réception par la passerelle (`received`).
- Syslog RFC 3164 (pfSense, ancien auth.log) : ni année ni fuseau. Fuseau
  `NORMALIZER_SYSLOG_TIMEZONE` (UTC par défaut, qui est aussi l'heure du Sénégal) ; année de la
  réception, ou l'année précédente pour une ligne de décembre reçue en janvier.
- journald : `_SOURCE_REALTIME_TIMESTAMP`, sinon l'heure du journal transmise par l'agent.

## Enrichissement (C10)

| Champ | Origine |
|---|---|
| `baolsec.source.name` | `config.sources.name` |
| `baolsec.source.criticality` | `config.sources.criticality` si l'Administrateur l'a renseignée |
| `host.name` (ou `observer.name` pour un pare-feu) | `config.sources.host`, seulement si le journal ne nomme pas la machine |
| `baolsec.ip_scope.source` / `.destination` | `private` : réseaux privés, CGNAT, boucle locale, lien local, multidiffusion, ULA IPv6, plus `NORMALIZER_INTERNAL_NETWORKS` ; sinon `public` |

Le référentiel est relu toutes les 30 s : une criticité modifiée s'applique sans redémarrage.

## Journal applicatif JSON

Une ligne JSON par événement. Clés reconnues : horodatage `ts`, `timestamp`, `@timestamp` ou
`time` ; niveau `level` ; événement `event` (`login_succeeded`, `login_failed`…) ; adresse
`client_ip`, `ip` ou `remote_addr` ; compte `user` ou `username` ; motif `reason` ; texte
`message` ; application `app` ou `service`.

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `BROKER_URL`, `BROKER_TOKEN` | `nats://broker:4222`, — | broker |
| `NORMALIZER_SOURCE_REGISTRY` | `postgres` | `postgres` ou `file` |
| `NORMALIZER_POSTGRES_DSN` | — | compte `svc_normalisation`, lecture seule sur `config` |
| `NORMALIZER_SOURCES_FILE` | — | fichier de sources (mode `file`, même fichier que la passerelle) |
| `NORMALIZER_SOURCES_REFRESH_S` / `NORMALIZER_SOURCES_MAX_STALE_S` | 30 / 300 | cache des sources |
| `NORMALIZER_SYSLOG_TIMEZONE` | `UTC` | fuseau des horodatages Syslog sans fuseau |
| `NORMALIZER_INTERNAL_NETWORKS` | — | réseaux supplémentaires classés `private` (liste séparée par des virgules) |
| `NORMALIZER_FETCH_BATCH` | 200 | messages lus par requête au broker |
| `NORMALIZER_CONTRACTS_DIR` | `/opt/baolsec/contracts` | schémas des contrats (copiés dans l'image) |

## Supervision

Port interne 9000 : `/health` et `/metrics` (`baolsec_normalizer_events_total` par type de source
et issue, `_datasets_total`, `_rejections_total` par motif, `_seconds`, `_unknown_sources_total`,
`_sources_cache_age_seconds`, `_paused`).

Les événements sont contrôlés avec `jsonschema-rs` (validateur compilé) : environ 4 µs par
événement, contre 450 µs avec la bibliothèque `jsonschema`. Les tests contrôlent aussi chaque
sortie avec `jsonschema`.

## Tests

```bash
make fetch-datasets      # une fois : journaux publics dans test-data/public (non versionnés)
make normalizer-up
make test-normalizer     # unitaires + jeux publics + intégration
make bench-normalizer    # débit
```

Jeux publics (versions figées par commit dans `scripts/testing/fetch_public_datasets.sh`) :
Loghub OpenSSH et Linux, jeux de test iptables d'Elastic Beats, jeux de test pfSense d'Elastic
Integrations, 10 000 lignes de journal d'accès (Elastic Examples), EVTX-ATTACK-SAMPLES pour Windows
(fichiers EVTX réels convertis au format de l'agent).

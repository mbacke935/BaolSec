# C26-PRE2 — finalisation de l'environnement C26

## Décision

**PARTIELLEMENT PRÊT ; exécution C26 BLOQUÉE sur cet hôte.** Le relevé du 16 novembre
2026 indique 2,1 Gio de RAM disponibles et 3,8 Gio de swap utilisés sur 4 Gio. Le
seuil impératif de 8 Gio réellement libres n'est pas atteint ; aucun build ni conteneur
C26 n'a donc été lancé.

## Corrections isolées préparées

- `topology.c26.json` est montée seulement dans `baolsec-c26-broker-init`. Elle aligne
  les durables avec les valeurs des workers : `normalization`, `detection`,
  `incident-builder`, `coverage-worker-raw`, `coverage-worker-norm`,
  `indexing-normalized`, `indexing-alerts` et `indexing-incidents`.
- Elle ajoute le stream `INCIDENTS`, requis par l'indexing-worker. Aucun producteur
  `incidents` n'a été trouvé : l'indexation d'incidents reste non vérifiée.
- `db-bootstrap` charge idempotemment sources et règles après `db-migrate`, dans
  PostgreSQL C26 seulement.
- `generate-test-tls.sh` génère exclusivement une AC, un certificat gateway et une
  source HTTPS de test C26 dans un chemin absolu local ; clés et jetons ne sont pas
  affichés ni versionnés.

## Contrôles statiques

| Contrôle | Résultat |
|---|---|
| `docker compose ... compose.prepared.yaml --profile observability config -q` | RÉUSSI ; 15 services, 5 volumes dédiés |
| JSON topologie | RÉUSSI |
| `bash -n generate-test-tls.sh` | RÉUSSI |
| `.env` et Compose existants | inchangés |
| `git diff --check` | RÉUSSI |

## Limites et reprise

Builds, téléchargement OpenSearch, TLS réel, migrations, JetStream, flux, API et
supervision sont non exécutés. Utiliser une machine ayant au moins 8 Gio réellement
libres, générer les artefacts TLS C26, créer un fichier local de variables, puis
demander l'autorisation de construire et démarrer seulement le projet `baolsec-c26`.

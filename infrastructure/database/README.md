# Base PostgreSQL

Schéma de C4 : une base `baolsec`, quatre schémas (`acces`, `config`, `incidents`, `couverture`),
un compte par service. Ce socle de C19 est réalisé avant C12 à C17, qui en ont besoin ; OpenSearch
et l'indexation restent dans C19.

| Fichier | Rôle |
|---|---|
| `sql/0001_acces.sql` … `0004_couverture.sql` | Un fichier par schéma : tables, énumérations, contraintes de C4 |
| `sql/0005_comptes.sql` | Comptes `svc_*` et leurs droits (C4 2.2) |
| `migrations/` | Révisions Alembic, une par fichier SQL ; suivi dans `public.alembic_version` |
| `migrate.py` | `alembic upgrade head`, puis mots de passe des comptes depuis l'environnement |
| `seed_dev.py` | Copie `infrastructure/tls/dev/sources.json` dans `config.sources` (développement) |
| `Dockerfile` | Image du conteneur ponctuel `db-migrate` |

## Démarrer

```bash
# dans .env : POSTGRES_PASSWORD et SVC_*_PASSWORD (openssl rand -hex 24 pour chacun)
make db-up        # PostgreSQL 17 + migrations + mots de passe
make db-seed      # sources de développement (après make gateway-dev)
make test-db      # schéma, contraintes, droits, lecture du référentiel par la passerelle et la normalisation
make db-psql      # console
```

Les mots de passe entrent dans des URL de connexion : un mot de passe hexadécimal évite tout
caractère à échapper. Le port 5432 n'est publié que sur `127.0.0.1` ; si un PostgreSQL local
l'occupe déjà, l'arrêter (`sudo systemctl stop postgresql`) avant `make db-up`.

## Droits des comptes

| Compte | Écriture | Lecture |
|---|---|---|
| `svc_api` | `acces`, `config` (jamais de suppression d'utilisateur, de source ou de règle ; journal d'audit en ajout seul) | `incidents`, `couverture` |
| `svc_passerelle` | — | `config.sources`, `config.source_credentials` |
| `svc_normalisation` | — | `config.sources` |
| `svc_detection` | — | `config.rules`, `config.rule_versions`, `config.rule_requirements` |
| `svc_incidents` | `incidents` (sans suppression) | `config.rules`, `config.settings`, `acces.users` (sans le mot de passe haché) |
| `svc_couverture` | `couverture` | `config.sources`, `config.rules`, `config.rule_requirements` |

`config.settings` est lu par `svc_incidents` pour les paramètres de corrélation (fenêtre de 30 min,
durée maximale de 24 h, valeurs génériques, enchaînements d'activités : C3 section 3.8), créés par
la migration 0002 avec les valeurs de C3.

## Modifier le schéma

Ajouter un fichier `sql/0006_….sql` et la révision correspondante dans `migrations/versions/`
(même modèle que les révisions existantes), puis `make db-migrate`. Une migration déjà appliquée
n'est jamais modifiée. Le retour arrière d'une révision supprime son schéma ; celui de 0005 retire
les droits dans la base sans supprimer les comptes, qui sont communs au serveur.

## Passerelle et normalisation

Elles lisent toujours le fichier `sources.json` par défaut, car les tests de C6 et C10 le modifient
pendant leur exécution. Pour qu'elles lisent la base : `make db-seed`, puis dans `.env`
`GATEWAY_SOURCE_REGISTRY=postgres`, `GATEWAY_POSTGRES_DSN=postgresql://svc_passerelle:…@postgresql:5432/baolsec`
et l'équivalent `NORMALIZER_*` avec `svc_normalisation`.

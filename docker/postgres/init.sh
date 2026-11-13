#!/bin/bash
# BaolSec — Initialisation PostgreSQL (C18)
# Crée les schémas, l'extension uuid-ossp et les 6 comptes de service
# (principe du moindre privilège, C3/C4 §2.2).
#
# Le rôle propriétaire POSTGRES_USER (baolsec) exécute les migrations Alembic
# et possède les tables. Les comptes svc_* ne reçoivent que les droits
# strictement nécessaires, y compris sur les tables créées ensuite par le
# propriétaire (ALTER DEFAULT PRIVILEGES FOR ROLE).
#
# Les mots de passe ne sont jamais écrits dans le dépôt : ils viennent de
# l'environnement (SVC_*_PASSWORD, passés par compose.yaml).
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS acces;
CREATE SCHEMA IF NOT EXISTS config;
CREATE SCHEMA IF NOT EXISTS incidents;
CREATE SCHEMA IF NOT EXISTS couverture;

-- ── Comptes de service (C4 §2.2) ─────────────────────────────────────────────
DO \$do\$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['svc_api','svc_passerelle','svc_normalisation','svc_detection','svc_incidents','svc_couverture'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I LOGIN', r);
    END IF;
  END LOOP;
END
\$do\$;

ALTER ROLE svc_api           WITH PASSWORD '${SVC_API_PASSWORD}';
ALTER ROLE svc_passerelle    WITH PASSWORD '${SVC_PASSERELLE_PASSWORD}';
ALTER ROLE svc_normalisation WITH PASSWORD '${SVC_NORMALISATION_PASSWORD}';
ALTER ROLE svc_detection     WITH PASSWORD '${SVC_DETECTION_PASSWORD}';
ALTER ROLE svc_incidents     WITH PASSWORD '${SVC_INCIDENTS_PASSWORD}';
ALTER ROLE svc_couverture    WITH PASSWORD '${SVC_COUVERTURE_PASSWORD}';

-- ── USAGE sur les schémas nécessaires ────────────────────────────────────────
GRANT USAGE ON SCHEMA acces, config, incidents, couverture TO svc_api;
GRANT USAGE ON SCHEMA incidents, config, acces TO svc_incidents;
GRANT USAGE ON SCHEMA couverture, config TO svc_couverture;
GRANT USAGE ON SCHEMA config TO svc_passerelle, svc_normalisation, svc_detection;

-- ── Droits par défaut sur les tables créées ensuite par le propriétaire ──────
-- svc_api : écrivain de acces + config ; lecture incidents + couverture
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA acces, config
  GRANT SELECT, INSERT, UPDATE ON TABLES TO svc_api;
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA incidents, couverture
  GRANT SELECT ON TABLES TO svc_api;

-- svc_incidents : écrivain de incidents ; lecture config + acces
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA incidents
  GRANT SELECT, INSERT, UPDATE ON TABLES TO svc_incidents;
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA config, acces
  GRANT SELECT ON TABLES TO svc_incidents;

-- svc_couverture : écrivain de couverture ; lecture config
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA couverture
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO svc_couverture;
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA config
  GRANT SELECT ON TABLES TO svc_couverture;

-- svc_passerelle / svc_normalisation / svc_detection : lecture seule de config
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA config
  GRANT SELECT ON TABLES TO svc_passerelle, svc_normalisation, svc_detection;

-- ── Séquences pour les écrivains ─────────────────────────────────────────────
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA acces, config
  GRANT USAGE, SELECT ON SEQUENCES TO svc_api;
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA incidents
  GRANT USAGE, SELECT ON SEQUENCES TO svc_incidents;
ALTER DEFAULT PRIVILEGES FOR ROLE "$POSTGRES_USER" IN SCHEMA couverture
  GRANT USAGE, SELECT ON SEQUENCES TO svc_couverture;
SQL

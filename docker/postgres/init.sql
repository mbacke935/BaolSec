-- BaolSec — Initialisation PostgreSQL (C18)
-- Crée les schémas et l'extension uuid-ossp.
-- Les tables sont créées par les migrations Alembic (C19).

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS acces;
CREATE SCHEMA IF NOT EXISTS config;
CREATE SCHEMA IF NOT EXISTS incidents;
CREATE SCHEMA IF NOT EXISTS couverture;

-- Accord des droits au rôle applicatif
GRANT USAGE ON SCHEMA acces, config, incidents, couverture TO baolsec;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA acces TO baolsec;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA config TO baolsec;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA incidents TO baolsec;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA couverture TO baolsec;
ALTER DEFAULT PRIVILEGES IN SCHEMA acces GRANT ALL ON TABLES TO baolsec;
ALTER DEFAULT PRIVILEGES IN SCHEMA config GRANT ALL ON TABLES TO baolsec;
ALTER DEFAULT PRIVILEGES IN SCHEMA incidents GRANT ALL ON TABLES TO baolsec;
ALTER DEFAULT PRIVILEGES IN SCHEMA couverture GRANT ALL ON TABLES TO baolsec;

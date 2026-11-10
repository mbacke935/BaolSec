-- Schéma config (C4 4.2, 5.2) — écrivain : API
CREATE SCHEMA config;
CREATE TYPE config.source_type AS ENUM ('linux', 'windows', 'firewall', 'http');
CREATE TYPE config.transport AS ENUM ('https', 'syslog');
CREATE TYPE config.ingestion_mode AS ENUM ('direct', 'rejeu');
CREATE TYPE config.credential_type AS ENUM ('token', 'client_cert');
CREATE TYPE config.criticality AS ENUM ('faible', 'moyenne', 'elevee', 'critique');
CREATE TYPE config.rule_type AS ENUM ('simple', 'window');
CREATE TYPE config.severity AS ENUM ('faible', 'moyenne', 'elevee', 'critique');

CREATE TABLE config.sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  source_type config.source_type NOT NULL,
  transport config.transport NOT NULL,
  ingestion_mode config.ingestion_mode NOT NULL DEFAULT 'direct',
  host text,
  criticality config.criticality,
  silence_threshold_s integer NOT NULL DEFAULT 600 CHECK (silence_threshold_s > 0),
  expected_min_events_per_h integer CHECK (expected_min_events_per_h >= 0),
  is_enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE config.source_credentials (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES config.sources(id),
  credential_type config.credential_type NOT NULL,
  secret_hash text,
  cert_fingerprint text UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz,
  revoked_at timestamptz,
  CHECK ((credential_type = 'token' AND secret_hash IS NOT NULL)
      OR (credential_type = 'client_cert' AND cert_fingerprint IS NOT NULL))
);
CREATE INDEX ON config.source_credentials (source_id);

-- Deux identifiants actifs au plus par source (C4 4.5, RG-04) : la ligne de la source est
-- verrouillée pour que deux ajouts simultanés ne passent pas chacun le contrôle.
CREATE FUNCTION config.check_active_credentials() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n integer;
BEGIN
  IF NEW.revoked_at IS NOT NULL THEN RETURN NEW; END IF;
  PERFORM 1 FROM config.sources WHERE id = NEW.source_id FOR UPDATE;
  SELECT count(*) INTO n FROM config.source_credentials
   WHERE source_id = NEW.source_id AND revoked_at IS NULL AND id <> NEW.id;
  IF n >= 2 THEN
    RAISE EXCEPTION 'la source % a déjà deux identifiants actifs', NEW.source_id USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER source_credentials_max_actifs BEFORE INSERT OR UPDATE ON config.source_credentials
  FOR EACH ROW EXECUTE FUNCTION config.check_active_credentials();

CREATE TABLE config.rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  description text,
  rule_type config.rule_type NOT NULL,
  severity config.severity NOT NULL,
  is_enabled boolean NOT NULL DEFAULT true,
  current_version integer NOT NULL DEFAULT 1,
  created_by uuid REFERENCES acces.users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE config.rule_versions (
  rule_id uuid NOT NULL REFERENCES config.rules(id),
  version integer NOT NULL CHECK (version >= 1),
  definition_yaml text NOT NULL,
  checksum text NOT NULL,
  created_by uuid REFERENCES acces.users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (rule_id, version)
);
CREATE TABLE config.rule_requirements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id uuid NOT NULL REFERENCES config.rules(id) ON DELETE CASCADE,
  source_type config.source_type NOT NULL,
  source_id uuid REFERENCES config.sources(id),
  required_fields text[]
);
CREATE INDEX ON config.rule_requirements (rule_id);
CREATE TABLE config.settings (
  key text PRIMARY KEY,
  value jsonb NOT NULL,
  updated_by uuid REFERENCES acces.users(id),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Paramètres de corrélation de C3 (section 3.8), modifiables ensuite par l'Administrateur
INSERT INTO config.settings (key, value) VALUES
  ('correlation.window_minutes', '30'),
  ('correlation.max_incident_hours', '24'),
  ('correlation.generic_values', '["anonymous", "-", "—", "n/a", "system", "unknown", "localhost"]'),
  ('correlation.activity_chains', '[["authentication", "authentication"], ["authentication", "process"], ["authentication", "network"], ["web", "process"]]');

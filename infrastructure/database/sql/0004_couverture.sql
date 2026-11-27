-- Schéma couverture (C4 4.4, 5.4) — écrivain : service Couverture
CREATE SCHEMA IF NOT EXISTS couverture;
CREATE TYPE couverture.state AS ENUM ('INCONNUE', 'ACTIVE', 'SILENCIEUSE', 'FLUX_INCOMPLET', 'DESACTIVEE');
CREATE TYPE couverture.cause AS ENUM ('silence', 'flux_incomplet', 'desactivee');

CREATE TABLE couverture.coverage_state (
  source_id uuid PRIMARY KEY REFERENCES config.sources(id),
  state couverture.state NOT NULL DEFAULT 'INCONNUE',
  state_since timestamptz NOT NULL DEFAULT now(),
  last_received_at timestamptz,
  last_normalized_at timestamptz,
  last_evaluated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE couverture.coverage_state_history (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_id uuid NOT NULL REFERENCES config.sources(id),
  from_state couverture.state NOT NULL,
  to_state couverture.state NOT NULL,
  reason text NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON couverture.coverage_state_history (source_id, changed_at);
CREATE TABLE couverture.coverage_stats (
  source_id uuid NOT NULL REFERENCES config.sources(id),
  bucket_start timestamptz NOT NULL,
  received_count bigint NOT NULL DEFAULT 0,
  normalized_count bigint NOT NULL DEFAULT 0,
  rejected_count bigint NOT NULL DEFAULT 0,
  error_count bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (source_id, bucket_start)
);
CREATE TABLE couverture.coverage_affected_rules (
  source_id uuid NOT NULL REFERENCES config.sources(id),
  rule_id uuid NOT NULL REFERENCES config.rules(id),
  since timestamptz NOT NULL,
  cause couverture.cause NOT NULL,
  resolved_at timestamptz,
  PRIMARY KEY (source_id, rule_id, since)
);
CREATE TABLE couverture.coverage_batches (
  consumer text NOT NULL,
  batch_id bigint NOT NULL,
  committed_at timestamptz NOT NULL DEFAULT now(),
  stream_seqs bigint[] NOT NULL,
  PRIMARY KEY (consumer, batch_id)
);

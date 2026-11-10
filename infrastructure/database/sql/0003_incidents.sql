-- Schéma incidents (C4 4.3, 5.3) — écrivain : service Incidents
CREATE SCHEMA incidents;
CREATE TYPE incidents.alert_status AS ENUM ('nouvelle', 'en_cours', 'cloturee');
CREATE TYPE incidents.incident_status AS ENUM ('ouvert', 'en_cours', 'clos');
CREATE TYPE incidents.entry_type AS ENUM ('event', 'alert', 'status_change', 'comment', 'correlation', 'conflict');
CREATE TYPE incidents.command_type AS ENUM ('changer_statut', 'commenter', 'clore', 'rouvrir', 'assigner', 'statut_alerte', 'assigner_alerte');
CREATE TYPE incidents.command_result AS ENUM ('acceptee', 'refusee', 'en_erreur');

CREATE TABLE incidents.alert_state (
  alert_id text PRIMARY KEY,
  rule_id uuid NOT NULL REFERENCES config.rules(id),
  severity config.severity NOT NULL,
  triggered_at timestamptz NOT NULL,
  status incidents.alert_status NOT NULL DEFAULT 'nouvelle',
  assigned_to uuid REFERENCES acces.users(id),
  status_changed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON incidents.alert_state (status, triggered_at);
CREATE TABLE incidents.incidents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  status incidents.incident_status NOT NULL DEFAULT 'ouvert',
  severity config.severity NOT NULL,
  correlation_context jsonb NOT NULL,
  opened_at timestamptz NOT NULL,
  last_activity_at timestamptz NOT NULL,
  closed_at timestamptz,
  assigned_to uuid REFERENCES acces.users(id),
  CHECK ((status = 'clos') = (closed_at IS NOT NULL))
);
CREATE INDEX ON incidents.incidents (status, last_activity_at);
CREATE TABLE incidents.incident_alerts (
  incident_id uuid NOT NULL REFERENCES incidents.incidents(id),
  alert_id text NOT NULL UNIQUE REFERENCES incidents.alert_state(alert_id),
  attached_at timestamptz NOT NULL DEFAULT now(),
  criteria jsonb NOT NULL,
  PRIMARY KEY (incident_id, alert_id)
);
CREATE TABLE incidents.incident_timeline (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  incident_id uuid NOT NULL REFERENCES incidents.incidents(id),
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  entry_type incidents.entry_type NOT NULL,
  alert_id text REFERENCES incidents.alert_state(alert_id),
  event_id text,
  summary text NOT NULL,
  justification jsonb,
  actor_id uuid REFERENCES acces.users(id)
);
CREATE INDEX ON incidents.incident_timeline (incident_id, occurred_at);
CREATE TABLE incidents.incident_comments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  incident_id uuid NOT NULL REFERENCES incidents.incidents(id),
  author_id uuid NOT NULL REFERENCES acces.users(id),
  body text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE incidents.incident_commands (
  command_id uuid PRIMARY KEY,
  command_type incidents.command_type NOT NULL,
  incident_id uuid REFERENCES incidents.incidents(id),
  alert_id text REFERENCES incidents.alert_state(alert_id),
  issued_by uuid NOT NULL REFERENCES acces.users(id),
  payload jsonb,
  result incidents.command_result NOT NULL,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CHECK (incident_id IS NOT NULL OR alert_id IS NOT NULL)
);

-- Schéma acces (C4 4.1, 5.1) — écrivain : API
CREATE SCHEMA IF NOT EXISTS acces;
CREATE TYPE acces.outcome AS ENUM ('succes', 'refus', 'echec');

CREATE TABLE acces.roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  description text
);
CREATE TABLE acces.permissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code text NOT NULL UNIQUE,
  description text
);
CREATE TABLE acces.role_permissions (
  role_id uuid NOT NULL REFERENCES acces.roles(id) ON DELETE CASCADE,
  permission_id uuid NOT NULL REFERENCES acces.permissions(id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_id)
);
CREATE TABLE acces.users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username text NOT NULL UNIQUE,
  email text UNIQUE,
  password_hash text NOT NULL,
  role_id uuid NOT NULL REFERENCES acces.roles(id),
  is_active boolean NOT NULL DEFAULT true,
  failed_attempts integer NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
  locked_until timestamptz,
  last_login_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE acces.user_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES acces.users(id),
  refresh_token_hash text NOT NULL,
  issued_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz
);
CREATE INDEX ON acces.user_sessions (user_id);
CREATE TABLE acces.audit_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  actor_id uuid REFERENCES acces.users(id) ON DELETE SET NULL,
  actor_username text NOT NULL,
  action text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  outcome acces.outcome NOT NULL,
  details jsonb,
  client_ip inet
);
CREATE INDEX ON acces.audit_log (occurred_at);

-- Deux rôles seulement dans le prototype (C1, C2)
INSERT INTO acces.roles (name, description) VALUES
  ('Administrateur', 'Utilisateurs, sources, règles et paramètres'),
  ('Analyste', 'Alertes, recherche, incidents, chronologie et couverture');

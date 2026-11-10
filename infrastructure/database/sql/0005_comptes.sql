-- Un compte par service, avec les seuls droits nécessaires (C4 section 2.2).
-- Les mots de passe ne sont jamais dans les migrations : migrate.py les pose depuis l'environnement.
-- Un compte sans mot de passe ne peut pas se connecter.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['svc_api', 'svc_passerelle', 'svc_normalisation', 'svc_detection', 'svc_incidents', 'svc_couverture'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I LOGIN', r);
    END IF;
  END LOOP;
END $$;

-- API : écrivain de acces et config ; lecture des incidents et de la couverture ; journal d'audit en ajout seul
GRANT USAGE ON SCHEMA acces, config, incidents, couverture TO svc_api;
-- Utilisateurs, sources et règles ne sont jamais supprimés, seulement désactivés (C4 2.2) : pas de DELETE sur ces tables.
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA acces, config TO svc_api;
GRANT DELETE ON acces.role_permissions, acces.user_sessions, config.rule_requirements, config.settings TO svc_api;
REVOKE UPDATE ON acces.audit_log FROM svc_api;
GRANT SELECT ON ALL TABLES IN SCHEMA incidents, couverture TO svc_api;

-- Passerelle (C6) et normalisation (C10) : lecture du référentiel des sources
GRANT USAGE ON SCHEMA config TO svc_passerelle, svc_normalisation;
GRANT SELECT ON config.sources, config.source_credentials TO svc_passerelle;
GRANT SELECT ON config.sources TO svc_normalisation;

-- Détection (C12) : lecture des règles
GRANT USAGE ON SCHEMA config TO svc_detection;
GRANT SELECT ON config.rules, config.rule_versions, config.rule_requirements TO svc_detection;

-- Incidents (C15 à C17) : écrivain du schéma incidents ; lecture des règles et des utilisateurs (C4),
-- et des paramètres de corrélation (config.settings, ajouté pour C16)
GRANT USAGE ON SCHEMA config, acces, incidents TO svc_incidents;
GRANT SELECT ON config.rules, config.settings TO svc_incidents;
GRANT SELECT (id, username, role_id, is_active) ON acces.users TO svc_incidents;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA incidents TO svc_incidents;

-- Couverture (C17) : écrivain du schéma couverture ; lecture des sources et des règles
GRANT USAGE ON SCHEMA config, couverture TO svc_couverture;
GRANT SELECT ON config.sources, config.rules, config.rule_requirements TO svc_couverture;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA couverture TO svc_couverture;

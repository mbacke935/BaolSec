-- Migration 0006 : table Outbox transactionnelle pour les incidents (C19).
--
-- Principe : lorsque l'Incident Builder crée ou modifie un incident, il insère
-- un événement dans cette table dans la MÊME transaction PostgreSQL.
-- Un publisher indépendant (OutboxPublisher) lit les lignes non publiées,
-- publie le snapshot sur NATS/INCIDENTS, puis marque la ligne comme publiée.
-- L'idempotence côté consommateur (IncidentIndexer) repose sur incident_id
-- en tant que _id OpenSearch (index avec écrasement si même incident_id).

CREATE TABLE incidents.incident_outbox (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id        uuid    NOT NULL DEFAULT gen_random_uuid(),
    incident_id     uuid    NOT NULL REFERENCES incidents.incidents(id),
    event_type      text    NOT NULL,          -- 'created' | 'updated'
    payload         jsonb   NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    published_at    timestamptz,               -- NULL = non publié
    UNIQUE (event_id)
);

-- Index pour le publisher : récupère rapidement les lignes non publiées dans l'ordre d'insertion.
CREATE INDEX idx_incident_outbox_unpublished
    ON incidents.incident_outbox (id)
    WHERE published_at IS NULL;

-- Droits : svc_incidents écrit les lignes ; le publisher tourne sous le même compte.
GRANT SELECT, INSERT, UPDATE ON incidents.incident_outbox TO svc_incidents;
GRANT USAGE, SELECT ON SEQUENCE incidents.incident_outbox_id_seq TO svc_incidents;

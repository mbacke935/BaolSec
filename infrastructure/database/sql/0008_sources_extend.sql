-- Migration 0008 : métadonnées descriptives des sources (inventaire, C26).
--
-- Ces colonnes étaient créées par la chaîne de migrations racine `migrations/` (0002_sources_extend),
-- qu'aucun conteneur n'exécutait (db-migrate applique uniquement cette chaîne-ci). L'API
-- (routers/sources.py) les lit et les écrit pourtant : sans elles, GET /api/v1/sources répondait 500.
-- Elles sont donc rapatriées dans la chaîne officielle du schéma C4.
ALTER TABLE config.sources
    ADD COLUMN IF NOT EXISTS hostname    text,
    ADD COLUMN IF NOT EXISTS ip_address  inet,
    ADD COLUMN IF NOT EXISTS environment text
        CHECK (environment IN ('production', 'staging', 'test', 'developpement')),
    ADD COLUMN IF NOT EXISTS tags        text[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS responsible text;

-- Migration 0009 : un même jeton ne peut pas être actif deux fois (C26, réserve F-3).
--
-- La passerelle indexe son cache par empreinte (gateway/sources_cache) : deux identifiants actifs
-- portant le même secret_hash seraient confondus et les événements attribués à la mauvaise source,
-- sans erreur. cert_fingerprint est déjà UNIQUE depuis 0002 (y compris après révocation) ; seul
-- secret_hash restait sans contrainte. L'index est partiel : un jeton révoqué ne bloque rien.
CREATE UNIQUE INDEX IF NOT EXISTS uq_source_credentials_secret_hash_active
    ON config.source_credentials (secret_hash)
    WHERE revoked_at IS NULL AND secret_hash IS NOT NULL;

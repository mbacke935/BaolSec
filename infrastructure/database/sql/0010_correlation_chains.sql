-- Migration 0010 : enchaînements d'activités alignés sur C3 (table 7) et sur le service Incidents.
--
-- Le service Incidents lit désormais config.settings (C3 3.8) au lieu de ses seules constantes.
-- La valeur initiale de 0002 omettait deux enchaînements que le code appliquait déjà
-- (authentication → host, web → host) : sans eux, l'activation de la lecture des paramètres aurait
-- changé silencieusement le regroupement. La valeur n'est remplacée que si elle est encore celle
-- de 0002 : un réglage modifié par un administrateur est conservé.
UPDATE config.settings
   SET value = '[["authentication", "authentication"], ["authentication", "process"], ["authentication", "network"], ["authentication", "host"], ["web", "process"], ["web", "host"]]'::jsonb,
       updated_at = NOW()
 WHERE key = 'correlation.activity_chains'
   AND value = '[["authentication", "authentication"], ["authentication", "process"], ["authentication", "network"], ["web", "process"]]'::jsonb;

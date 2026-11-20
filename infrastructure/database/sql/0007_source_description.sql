-- Ajout de la description des sources (correction du contrat API).
ALTER TABLE config.sources
    ADD COLUMN description text;

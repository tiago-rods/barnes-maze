-- US-13: evidência da entrada física e métricas descoberta -> entrada.
-- Descobertas da US-11 e eventos legados continuam válidos com objeto vazio.
-- Valores ausentes (ex.: entrada sem descoberta anterior) ficam como null
-- nos detalhes, acompanhados das inconsistências; não viram zeros.

BEGIN;

ALTER TABLE evento_buraco
    ADD COLUMN details JSONB NOT NULL DEFAULT '{}'::JSONB
        CHECK (jsonb_typeof(details) = 'object');

COMMIT;

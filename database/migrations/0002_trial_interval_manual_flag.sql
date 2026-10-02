-- US-03: marca se o intervalo útil do trial (start_time_seconds/end_time_seconds,
-- já existentes desde o schema inicial) veio de ajuste manual do operador
-- (Cenário 2) em vez da detecção automática do evento S/soltura (RN03).
-- Default FALSE: um trial recém-carregado, sem recorte ainda resolvido,
-- não está "ajustado manualmente".

BEGIN;

ALTER TABLE trials
    ADD COLUMN interval_manually_adjusted BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;

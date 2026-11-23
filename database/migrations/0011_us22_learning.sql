-- US-22: estado explícito de censura e entropia persistida para leitura offline.
-- NULL = não avaliado; não inferir censura do event_ocurred legado ambíguo.
BEGIN;
ALTER TABLE trial_results
    ADD COLUMN primary_event BOOLEAN,
    ADD COLUMN total_event BOOLEAN,
    ADD COLUMN entropy_bits DOUBLE PRECISION
        CHECK (entropy_bits >= 0 AND entropy_bits < 'Infinity'::DOUBLE PRECISION);
COMMIT;

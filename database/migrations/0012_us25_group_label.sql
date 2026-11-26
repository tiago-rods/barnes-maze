BEGIN;

ALTER TABLE experiments
    ADD COLUMN group_label TEXT;

COMMIT;

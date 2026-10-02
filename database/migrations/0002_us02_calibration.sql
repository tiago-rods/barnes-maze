-- US-02: calibração da escala px→cm por montagem.
--
-- Reaproveita as colunas que a 0001 já reservou em maze_configs
-- (px_per_10cm, calibration_date, measured_error_pct) — não precisam de
-- migração. Esta migration só adiciona o que faltava: a referência de onde a
-- calibração foi feita (para `scale verify`/`metrics process` conferirem a
-- mesma resolução) e, em trial_results, o registro de qual escala cada
-- resultado usou. "Desatualizado" não é uma coluna: um trial_results fica
-- obsoleto quando calculated_at < maze_configs.calibration_date ou
-- px_per_10cm_used != maze_configs.px_per_10cm — comparação feita pela
-- aplicação, no mesmo espírito do comentário já existente sobre
-- measured_error_pct na 0001.

BEGIN;

ALTER TABLE maze_configs
    ADD COLUMN calibration_reference_video TEXT,
    ADD COLUMN calibration_reference_frame INTEGER CHECK (calibration_reference_frame >= 0),
    ADD COLUMN calibration_width_px INTEGER CHECK (calibration_width_px > 0),
    ADD COLUMN calibration_height_px INTEGER CHECK (calibration_height_px > 0);

ALTER TABLE trial_results
    ADD COLUMN calculated_at TIMESTAMPTZ,
    ADD COLUMN px_per_10cm_used DOUBLE PRECISION CHECK (px_per_10cm_used > 0),
    ADD COLUMN route_efficiency DOUBLE PRECISION CHECK (route_efficiency BETWEEN 0 AND 1);

COMMIT;

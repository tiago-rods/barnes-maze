-- US-18: distância total e velocidade média por trial, a partir da série da US-09.
--
-- Distância e velocidade reaproveitam distance_cm/speed_mean_cm da 0001. Falta só a
-- fração interpolada (US-18 RN05): a parte das amostras usadas na distância que veio
-- de linhas preenchidas pela US-10. NULL quando não se aplica — linhas antigas e as
-- do `metrics process` (US-02), que lê um CSV sem a marca de interpolação.
--
-- A ressalva de fps variável (RN07) NÃO é coluna: é derivada na leitura de
-- trials.fps_is_variable, como is_stale e a VIEW qualidade_pose. A série que gerou a
-- métrica tem a mesma marca do trial (o comando confere antes de calcular).

BEGIN;

ALTER TABLE trial_results
    ADD COLUMN interpolated_fraction DOUBLE PRECISION
        CHECK (interpolated_fraction BETWEEN 0 AND 1);

COMMIT;

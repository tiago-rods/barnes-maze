-- US-10: correções manuais de pose e qualidade de pose por trial.
--
-- Toda correção manual (RN05) é um ponto — focinho, centro do corpo ou base
-- da cauda — marcado pelo operador num quadro, em pixels do vídeo original.
-- Ela pertence a uma execução de revisão do MESMO trial (`execucao`, kind
-- 'processamento', parametros.comando = 'pose review'), pela mesma FK
-- composta de trial_results e evento_buraco (US-27). Assim o número final é
-- auditável: com que código, quando e quais pontos foram corrigidos.
--
-- A cobertura em si já existe desde a 0007 (`trials.cobertura_pose` +
-- `cobertura_execucao_id`). A marcação de qualidade (RN06) é DERIVADA na
-- leitura pela VIEW `qualidade_pose`, como a obsolescência da US-02 e a VIEW
-- `sessao`: nenhum booleano gravado que possa divergir da cobertura.

BEGIN;

CREATE TABLE correcao_pose (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trial_id INTEGER NOT NULL REFERENCES trials (id) ON DELETE CASCADE,
    execucao_id INTEGER NOT NULL,
    quadro INTEGER NOT NULL CHECK (quadro >= 0),
    ponto TEXT NOT NULL CHECK (ponto IN ('focinho', 'centro_corpo', 'base_cauda')),
    -- `< 'Infinity'` também recusa NaN, que o Postgres ordena acima de Infinity.
    x_px DOUBLE PRECISION NOT NULL CHECK (x_px >= 0 AND x_px < 'Infinity'::DOUBLE PRECISION),
    y_px DOUBLE PRECISION NOT NULL CHECK (y_px >= 0 AND y_px < 'Infinity'::DOUBLE PRECISION),
    CONSTRAINT correcao_pose_execucao_fk
        FOREIGN KEY (execucao_id, trial_id)
        REFERENCES execucao (id, trial_id) ON DELETE CASCADE,
    -- Numa mesma sessão de revisão, um ponto é marcado uma vez por quadro.
    -- Sessões posteriores podem remarcar: vale a da execução mais recente.
    UNIQUE (execucao_id, quadro, ponto)
);

CREATE INDEX idx_correcao_pose_trial_id ON correcao_pose (trial_id);

-- Registro de intervenção não se edita: corrigir de novo é outra sessão de
-- revisão, com outra execução. Exclusão só pela cadeia de posse (CASCADE).
CREATE FUNCTION reject_correcao_pose_update() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Correções de pose são imutáveis; registre uma nova revisão.'
        USING ERRCODE = '55000';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER correcao_pose_immutable
    BEFORE UPDATE ON correcao_pose
    FOR EACH ROW EXECUTE FUNCTION reject_correcao_pose_update();

-- Qualidade de pose de cada trial (RN06), a partir da execução que calculou a
-- cobertura: o relatório dela (`metadata.qualidade_pose`, gravado por
-- `pose series`/`pose review`) traz o mínimo vigente e os trechos ainda não
-- revisados. Fonte única da marcação para o catálogo, as métricas e a
-- exportação (US-25).
CREATE VIEW qualidade_pose AS
SELECT t.id AS trial_id,
       t.cobertura_pose,
       t.cobertura_execucao_id,
       (e.metadata #>> '{qualidade_pose,cobertura_minima}')::DOUBLE PRECISION
           AS cobertura_minima,
       (e.metadata #>> '{qualidade_pose,trechos_pendentes}')::INTEGER AS trechos_pendentes,
       CASE
           WHEN t.cobertura_pose IS NULL OR NOT (e.metadata ? 'qualidade_pose') THEN NULL
           WHEN (e.metadata #>> '{qualidade_pose,trechos_pendentes}')::INTEGER > 0
               THEN 'revisao_pendente'
           WHEN t.cobertura_pose
                < (e.metadata #>> '{qualidade_pose,cobertura_minima}')::DOUBLE PRECISION
               THEN 'insuficiente'
           ELSE 'suficiente'
       END AS qualidade
FROM trials t
LEFT JOIN execucao e ON e.id = t.cobertura_execucao_id;

COMMIT;

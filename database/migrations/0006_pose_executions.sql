-- US-07 / US-08: auditoria de treino, avaliação e inferência de pose.
-- Um registro por tentativa terminada, sem sobrescrever tentativas anteriores.
-- Os pesos permanecem em models/ (fora do Git); aqui fica seu identificador
-- e o manifesto de proveniência, não o conteúdo binário dos artefatos.

BEGIN;

-- A FK composta impede associar a execução à montagem errada de um trial.
ALTER TABLE trials
    ADD CONSTRAINT trials_id_maze_config_unique UNIQUE (id, maze_config_id);

CREATE TABLE execucao (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('treino', 'avaliacao', 'inferencia')),
    model_id TEXT NOT NULL
        CHECK (model_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'),
    maze_config_id INTEGER NOT NULL REFERENCES maze_configs (id) ON DELETE CASCADE,
    trial_id INTEGER,
    status TEXT NOT NULL CHECK (status IN ('concluido', 'falhou')),
    duration_seconds DOUBLE PRECISION
        CHECK (duration_seconds >= 0 AND duration_seconds < 'Infinity'::DOUBLE PRECISION),
    artifact_path TEXT CHECK (length(btrim(artifact_path)) > 0),
    metadata JSONB NOT NULL CHECK (jsonb_typeof(metadata) = 'object')
        CHECK (NOT (metadata ? 'run_id') OR
               (jsonb_typeof(metadata -> 'run_id') = 'string'
                AND length(btrim(metadata ->> 'run_id')) BETWEEN 1 AND 256)),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT execucao_trial_montagem_fk
        FOREIGN KEY (trial_id, maze_config_id)
        REFERENCES trials (id, maze_config_id) ON DELETE CASCADE,
    CONSTRAINT execucao_treino_por_montagem
        CHECK (kind <> 'treino' OR trial_id IS NULL),
    CONSTRAINT execucao_inferencia_trial
        CHECK (kind <> 'inferencia' OR trial_id IS NOT NULL),
    CONSTRAINT execucao_inferencia_concluida
        CHECK (kind <> 'inferencia' OR status <> 'concluido'
               OR (duration_seconds IS NOT NULL AND artifact_path IS NOT NULL))
);

CREATE INDEX idx_execucao_model_id ON execucao (model_id);
CREATE INDEX idx_execucao_trial_id ON execucao (trial_id);
CREATE INDEX idx_execucao_maze_config_id ON execucao (maze_config_id);
-- register-run pode repetir após uma queda entre o COMMIT e o recibo local.
-- O identificador estável impede duplicação sem sobrescrever a proveniência.
CREATE UNIQUE INDEX idx_execucao_kind_run_id
    ON execucao (kind, (metadata ->> 'run_id')) WHERE metadata ? 'run_id';

-- O histórico é de acréscimo: uma nova tentativa gera outra linha. A exclusão
-- segue a cadeia de posse já adotada no schema (experiment/montagem/trial).
CREATE FUNCTION reject_execucao_update() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Execuções de pose são imutáveis; registre uma nova tentativa.'
        USING ERRCODE = '55000';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER execucao_immutable
    BEFORE UPDATE ON execucao
    FOR EACH ROW EXECUTE FUNCTION reject_execucao_update();

COMMIT;

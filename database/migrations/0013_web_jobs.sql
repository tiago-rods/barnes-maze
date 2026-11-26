-- Auditoria de jobs em segundo plano do wizard web (RQ + Redis).
--
-- O status/resultado do RQ em si fica no Redis, com TTL — some depois de um
-- tempo. Esta tabela é o registro permanente no Postgres: toda submissão de
-- job (sucesso ou falha) fica rastreável no dashboard mesmo após o Redis
-- expirar o resultado. Não substitui `execucao` (US-27): `execucao` é o
-- registro imutável de um processamento bem-sucedido, reaproveitável por
-- qualquer interface; `jobs` é efêmero por natureza do lado web, só serve
-- para "o que foi submetido e o que aconteceu com isso" na UI.
--
-- `status` usa o mesmo vocabulário de `rq.job.Job.get_status()`
-- (queued/started/finished/failed) de propósito, para não exigir tradução
-- entre o Redis e o Postgres.
BEGIN;

CREATE TABLE jobs (
    id BIGSERIAL PRIMARY KEY,
    rq_job_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (kind IN (
        'video_load', 'pose_infer', 'pose_series', 'pose_review_save',
        'events_discover', 'events_enter', 'metrics_displacement',
        'strategy_classify'
    )),
    trial_id INTEGER REFERENCES trials (id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'started', 'finished', 'failed')),
    execucao_id INTEGER,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE INDEX idx_jobs_trial_id ON jobs (trial_id);
CREATE INDEX idx_jobs_status ON jobs (status);

COMMIT;

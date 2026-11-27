-- Novos tipos de job do wizard web:
--   pose_demo      — trajetória sintética de demonstração (sem modelo de pose treinado);
--   trial_metrics  — métricas consolidadas de um trial (US-16/17/18/19/20) gravadas numa
--                    única execução, para a leitura "linha mais recente" da US-22.
BEGIN;

ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK (kind IN (
    'video_load', 'pose_infer', 'pose_demo', 'pose_series', 'pose_review_save',
    'events_discover', 'events_enter', 'metrics_displacement',
    'strategy_classify', 'trial_metrics'
));

COMMIT;

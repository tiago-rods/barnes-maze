-- US-27: proveniência de toda execução e catálogo de trials.
--
-- Aplicável tanto num banco vazio (0001..0007 em sequência) quanto num banco
-- que já tem dados das histórias anteriores: cada métrica já gravada recebe
-- uma execução "legado" ANTES de `trial_results.execucao_id` virar NOT NULL.
--
-- Correspondência entre o esquema do escopo (definicao-projeto.md) e as
-- tabelas reais — nomes existentes mantidos, ver docs/DER.md:
--   animal → subjects · montagem → maze_configs (+ holes, escala da US-02)
--   sessao → VIEW sessao (derivada de trials) · trial → trials
--   metrica → trial_results (agora uma linha por trial, por execução)
--   evento_buraco → evento_buraco (nova) · execucao → execucao (da 0006)

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. execucao: passa a registrar também o processamento de trials (RN01).
-- ---------------------------------------------------------------------------

ALTER TABLE execucao DROP CONSTRAINT execucao_kind_check;
ALTER TABLE execucao ADD CONSTRAINT execucao_kind_check
    CHECK (kind IN ('treino', 'avaliacao', 'inferencia', 'processamento'));

-- Processar uma trajetória já extraída não usa modelo de pose; quando usar
-- (US-09 em diante), o model_id é registrado. Pose continua exigindo modelo.
ALTER TABLE execucao ALTER COLUMN model_id DROP NOT NULL;
ALTER TABLE execucao ADD CONSTRAINT execucao_modelo_pose
    CHECK (kind = 'processamento' OR model_id IS NOT NULL);
ALTER TABLE execucao ADD CONSTRAINT execucao_processamento_trial
    CHECK (kind <> 'processamento' OR trial_id IS NOT NULL);

-- Campos que antes ficavam só dentro de `metadata`, agora consultáveis
-- diretamente (Cenário 2: modelo, limiares e commit exatos de uma execução
-- antiga). `recorded_at` (da 0006) é a data do registro.
ALTER TABLE execucao
    ADD COLUMN git_commit TEXT CHECK (git_commit ~ '^[0-9a-f]{40}$'),
    -- NULL = desconhecido (sem git na máquina); nunca assumido limpo (RN05).
    ADD COLUMN git_dirty BOOLEAN,
    ADD COLUMN limiares JSONB CHECK (jsonb_typeof(limiares) = 'object'),
    ADD COLUMN limiares_sha256 TEXT CHECK (limiares_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN parametros JSONB CHECK (jsonb_typeof(parametros) = 'object'),
    ADD COLUMN video_hash TEXT,
    ADD COLUMN iniciado_em TIMESTAMPTZ;

-- Um processamento novo precisa carregar limiares e parâmetros; só as
-- execuções "legado" criadas abaixo, anteriores à US-27, ficam sem eles.
ALTER TABLE execucao ADD CONSTRAINT execucao_processamento_proveniencia
    -- `@>` (e não `->> 'legado' = 'true'`): sem a chave, a comparação daria
    -- NULL, e um CHECK que resulta em NULL aceita a linha.
    CHECK (kind <> 'processamento' OR metadata @> '{"legado": true}'
           OR (limiares IS NOT NULL AND limiares_sha256 IS NOT NULL
               AND parametros IS NOT NULL AND iniciado_em IS NOT NULL));

-- Alvo das FKs compostas abaixo: a execução de uma métrica/evento precisa
-- ser do MESMO trial.
ALTER TABLE execucao ADD CONSTRAINT execucao_id_trial_unique UNIQUE (id, trial_id);

-- Backfill do commit das execuções de pose já registradas (US-07 grava em
-- metadata.source; o treino, no próprio manifesto). A tabela é imutável por
-- trigger; ele é suspenso só dentro desta transação de migração.
ALTER TABLE execucao DISABLE TRIGGER execucao_immutable;
UPDATE execucao
SET git_commit = CASE
        WHEN COALESCE(metadata -> 'source' ->> 'git_commit', metadata ->> 'git_commit')
             ~ '^[0-9a-f]{40}$'
        THEN COALESCE(metadata -> 'source' ->> 'git_commit', metadata ->> 'git_commit')
    END,
    git_dirty = COALESCE(metadata -> 'source' ->> 'git_dirty',
                         metadata ->> 'git_dirty')::BOOLEAN
WHERE metadata ? 'source' OR metadata ? 'git_commit';
ALTER TABLE execucao ENABLE TRIGGER execucao_immutable;

-- ---------------------------------------------------------------------------
-- 2. Métrica: uma linha por trial, por execução; órfã é erro de esquema (RN02).
-- ---------------------------------------------------------------------------

ALTER TABLE trial_results ADD COLUMN execucao_id INTEGER;

-- Cada resultado anterior à US-27 ganha uma execução "legado" própria:
-- sem commit nem limiares (não foram registrados na época), mas marcada
-- como tal, para nunca ser tomada como reproduzível.
WITH legado AS (
    INSERT INTO execucao (
        kind, model_id, maze_config_id, trial_id, status, metadata, recorded_at
    )
    SELECT 'processamento', NULL, t.maze_config_id, t.id, 'concluido',
           jsonb_build_object(
               'legado', true,
               'run_id', 'legado-trial_results-' || tr.id,
               'origem', 'migração 0007: métrica gravada antes da US-27'
           ),
           COALESCE(tr.calculated_at, now())
    FROM trial_results tr
    JOIN trials t ON t.id = tr.trial_id
    RETURNING id, trial_id
)
UPDATE trial_results tr
SET execucao_id = legado.id
FROM legado
WHERE tr.trial_id = legado.trial_id;  -- ainda 1:1 por trial neste ponto

ALTER TABLE trial_results ALTER COLUMN execucao_id SET NOT NULL;
ALTER TABLE trial_results
    ADD CONSTRAINT trial_results_execucao_fk
        FOREIGN KEY (execucao_id, trial_id)
        REFERENCES execucao (id, trial_id) ON DELETE CASCADE,
    ADD CONSTRAINT trial_results_execucao_unique UNIQUE (execucao_id);

-- Reprocessar acrescenta uma linha (histórico) em vez de sobrescrever.
ALTER TABLE trial_results DROP CONSTRAINT trial_results_trial_id_key;
CREATE INDEX idx_trial_results_trial_id ON trial_results (trial_id);

-- ---------------------------------------------------------------------------
-- 3. evento_buraco: eventos por buraco ligados à execução (US-11 em diante).
-- ---------------------------------------------------------------------------

CREATE TABLE evento_buraco (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trial_id INTEGER NOT NULL REFERENCES trials (id) ON DELETE CASCADE,
    hole_id INTEGER NOT NULL REFERENCES holes (id) ON DELETE CASCADE,
    execucao_id INTEGER NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('descoberta', 'entrada')),
    quadro INTEGER NOT NULL CHECK (quadro >= 0),
    -- Segundos desde o início do intervalo útil (US-03 RN05), não do vídeo.
    t_s DOUBLE PRECISION NOT NULL CHECK (t_s >= 0 AND t_s < 'Infinity'::DOUBLE PRECISION),
    distancia_cm DOUBLE PRECISION CHECK (distancia_cm >= 0),
    angulo_deg DOUBLE PRECISION CHECK (angulo_deg >= 0 AND angulo_deg < 360),
    CONSTRAINT evento_buraco_execucao_fk
        FOREIGN KEY (execucao_id, trial_id)
        REFERENCES execucao (id, trial_id) ON DELETE CASCADE,
    UNIQUE (execucao_id, hole_id, tipo, quadro)
);

CREATE INDEX idx_evento_buraco_trial_id ON evento_buraco (trial_id);
CREATE INDEX idx_evento_buraco_execucao_id ON evento_buraco (execucao_id);

-- ---------------------------------------------------------------------------
-- 4. trials: cobertura de pose (US-10) e tamanho do arquivo (RN04).
-- ---------------------------------------------------------------------------

ALTER TABLE trials
    -- Fração de quadros do intervalo útil com pose válida; NULL até a US-10.
    ADD COLUMN cobertura_pose DOUBLE PRECISION
        CHECK (cobertura_pose >= 0 AND cobertura_pose <= 1),
    -- Execução que calculou a cobertura — do próprio trial (FK composta).
    ADD COLUMN cobertura_execucao_id INTEGER,
    -- Checagem barata do catálogo; o hash completo continua sendo a prova.
    -- NULL para trials carregados antes da US-27.
    ADD COLUMN file_size_bytes BIGINT CHECK (file_size_bytes > 0),
    ADD CONSTRAINT trials_cobertura_execucao_fk
        FOREIGN KEY (cobertura_execucao_id, id) REFERENCES execucao (id, trial_id),
    ADD CONSTRAINT trials_cobertura_com_execucao
        CHECK ((cobertura_pose IS NULL) = (cobertura_execucao_id IS NULL));

-- ---------------------------------------------------------------------------
-- 5. sessao: derivada dos trials (animal, número da sessão, data, tipo).
-- ---------------------------------------------------------------------------
-- VIEW, não tabela: os dados já estão em trials (day_number, phase); uma
-- tabela exigiria backfill e duas fontes da mesma informação. Não há data
-- de gravação no banco — a data é a do primeiro carregamento do dia.

CREATE VIEW sessao AS
SELECT t.experiment_id,
       s.id AS subject_id,
       s.name AS animal,
       t.day_number AS numero_sessao,
       string_agg(DISTINCT t.phase, ',' ORDER BY t.phase) AS tipo,
       min(t.loaded_at)::DATE AS data_primeiro_carregamento,
       count(*) AS trials
FROM trials t
LEFT JOIN subjects s ON s.experiment_id = t.experiment_id
GROUP BY t.experiment_id, s.id, s.name, t.day_number;

COMMIT;

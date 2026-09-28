-- Schema inicial do banco de dados do projeto Barnes Maze.
-- Gerado a partir de docs/DER.md.
--
-- Convenções adotadas nesta tradução do DER para SQL:
--   - Nomes de tabela no plural, snake_case (evita "user", palavra especial no Postgres).
--   - Chaves primárias via GENERATED ALWAYS AS IDENTITY (substitui SERIAL, padrão atual do Postgres).
--   - ON DELETE CASCADE ao longo de toda a cadeia de posse que o próprio DER descreve
--     (owns / has / defines / produces): apagar um experiment remove tudo que depende
--     dele. Ajustar tabela a tabela se algum dado precisar sobreviver ao "dono".
--   - CHECK nos campos que o DER já documentava como enumerados (phase, search_strategy)
--     ou com faixa fixa (angle_deg 0-360). Regras de negócio "medidas" (ex.: erro de
--     calibração < 3%) ficam para a aplicação validar, não para o banco.

BEGIN;

CREATE TABLE users (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE experiments (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    qts_trials INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_experiments_user_id ON experiments (user_id);

-- 1:1 com experiments — "sem reuso entre experimentos" (DER), por isso o UNIQUE na FK.
CREATE TABLE subjects (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    experiment_id INTEGER NOT NULL UNIQUE REFERENCES experiments (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    genotype TEXT,
    notes TEXT
);

CREATE TABLE maze_configs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    experiment_id INTEGER NOT NULL REFERENCES experiments (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    arena_diameter_cm DOUBLE PRECISION NOT NULL,
    hole_count INTEGER NOT NULL,
    hole_diameter_cm DOUBLE PRECISION NOT NULL,
    px_per_10cm DOUBLE PRECISION,        -- US-02: só existe depois da calibração
    threshold INTEGER,                   -- limiar de binarização usado no tracking
    min_area INTEGER,                    -- área mínima de contorno usada no tracking
    center_x_px INTEGER,
    center_y_px INTEGER,
    platform_radius_px DOUBLE PRECISION,
    calibration_date DATE,               -- US-02 RN02
    measured_error_pct DOUBLE PRECISION  -- US-02 RN04 (aceite: < 3%, validado pela aplicação)
);

CREATE INDEX idx_maze_configs_experiment_id ON maze_configs (experiment_id);

CREATE TABLE holes (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    maze_config_id INTEGER NOT NULL REFERENCES maze_configs (id) ON DELETE CASCADE,
    hole_number INTEGER NOT NULL,
    angle_deg DOUBLE PRECISION NOT NULL CHECK (angle_deg >= 0 AND angle_deg < 360),
    x_px INTEGER,
    y_px INTEGER,
    radius_px INTEGER,
    is_target BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (maze_config_id, hole_number)
);

CREATE INDEX idx_holes_maze_config_id ON holes (maze_config_id);

CREATE TABLE trials (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    experiment_id INTEGER NOT NULL REFERENCES experiments (id) ON DELETE CASCADE,
    maze_config_id INTEGER NOT NULL REFERENCES maze_configs (id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'loaded',
    phase TEXT NOT NULL CHECK (phase IN ('habituation', 'acquisition', 'probe')),
    day_number INTEGER NOT NULL CHECK (day_number > 0),
    trial_number_in_day INTEGER NOT NULL CHECK (trial_number_in_day > 0),
    start_time_seconds DOUBLE PRECISION, -- US-03: recorte do intervalo útil
    end_time_seconds DOUBLE PRECISION,
    content_hash TEXT NOT NULL UNIQUE,   -- US-01 RN05 — identifica o arquivo, não só o path
    width_px INTEGER NOT NULL,
    height_px INTEGER NOT NULL,
    fps_declared DOUBLE PRECISION NOT NULL,
    fps_real DOUBLE PRECISION NOT NULL,
    fps_is_variable BOOLEAN NOT NULL DEFAULT FALSE,
    frame_count INTEGER NOT NULL,
    duration_s DOUBLE PRECISION NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    trajectory_path TEXT                 -- preenchido pelo pipeline de pose (US-09/US-10)
);

CREATE INDEX idx_trials_experiment_id ON trials (experiment_id);
CREATE INDEX idx_trials_maze_config_id ON trials (maze_config_id);

CREATE TABLE trial_results (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trial_id INTEGER NOT NULL UNIQUE REFERENCES trials (id) ON DELETE CASCADE,
    distance_cm DOUBLE PRECISION,
    speed_mean_cm DOUBLE PRECISION,
    speed_max_cm DOUBLE PRECISION,
    path_tortuosity DOUBLE PRECISION,
    primary_latency_s DOUBLE PRECISION,
    total_latency_s DOUBLE PRECISION,    -- nulo na probe (ver trials.phase)
    primary_errors INTEGER,
    total_errors INTEGER,
    search_strategy TEXT CHECK (search_strategy IN ('random', 'serial', 'spatial')),
    heatmap_path TEXT,
    cox_test TEXT,
    event_ocurred BOOLEAN
);

CREATE TABLE hole_visits (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trial_result_id INTEGER NOT NULL REFERENCES trial_results (id) ON DELETE CASCADE,
    hole_id INTEGER NOT NULL REFERENCES holes (id) ON DELETE CASCADE,
    visit_order INTEGER NOT NULL CHECK (visit_order > 0),
    discovered_at_s DOUBLE PRECISION,       -- US-11 — descoberta (D), critério de percepção C1
    entered_at_s DOUBLE PRECISION NOT NULL, -- US-13 — entrada (E), critério físico C2
    duration_s DOUBLE PRECISION,
    UNIQUE (trial_result_id, visit_order)
);

CREATE INDEX idx_hole_visits_trial_result_id ON hole_visits (trial_result_id);
CREATE INDEX idx_hole_visits_hole_id ON hole_visits (hole_id);

COMMIT;

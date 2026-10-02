

```mermaid
erDiagram
    USER ||--o{ EXPERIMENT : owns

    EXPERIMENT ||--|| SUBJECT : "has exactly one"
    EXPERIMENT ||--o{ MAZE_CONFIG : "has (usually 1, new one if camera moves)"
    EXPERIMENT ||--o{ TRIAL : "has N (days/repeats)"

    MAZE_CONFIG ||--o{ HOLE : "defines N holes"
    MAZE_CONFIG ||--o{ TRIAL : "reused by (same camera setup)"

    TRIAL ||--|| TRIAL_RESULT : produces
    TRIAL_RESULT ||--o{ HOLE_VISIT : "ordered sequence of pokes"
    HOLE ||--o{ HOLE_VISIT : "visited in (across trials sharing its config)"

    USER {
        int id PK
        string email
        string name
    }
    EXPERIMENT {
        int id PK
        int user_id FK
        string name
        string description
        int qts_trials
    }
    SUBJECT {
        int id PK
        int experiment_id FK, UK "1:1 — sem reuso entre experimentos"
        string name
        string genotype
        string notes
    }
    MAZE_CONFIG {
        int id PK
        int experiment_id FK
        string name "ex. 'setup padrão' vs 'câmera reposicionada dia 4'"
        float arena_diameter_cm
        int hole_count
        float hole_diameter_cm
        float px_per_10cm
        int threshold
        int min_area
        int center_x_px
        int center_y_px
        float platform_radius_px
        date calibration_date "US-02 RN02 — data da calibração da escala"
        float measured_error_pct "US-02 RN04 — erro medido, deve ser < 3%"
        string calibration_reference_video "US-02 — vídeo/quadro usados na calibração"
        int calibration_reference_frame "US-02"
        int calibration_width_px "US-02 — resolução de referência da calibração"
        int calibration_height_px "US-02"
        string calibration_segments "US-02 RN04 — JSON dos 2 segmentos usados, para scale verify recusar reuso"
    }
    HOLE {
        int id PK
        int maze_config_id FK
        int hole_number "0..N-1 ao redor da plataforma (US-04 RN02)"
        float angle_deg "posição fixa, 0-360"
        int x_px
        int y_px
        int radius_px
        bool is_target "alvo fixo para o subject durante toda a aquisição"
    }
    TRIAL {
        int id PK
        int experiment_id FK
        int maze_config_id FK
        string filename
        string filepath
        string status
        string phase "habituation|acquisition|probe"
        int day_number
        int trial_number_in_day
        float start_time_seconds
        float end_time_seconds
        string content_hash "US-01 RN05 — sha256, detecta arquivo movido/alterado (US-27)"
        int width_px
        int height_px
        float fps_declared "US-01 RN01 — fps do cabeçalho do contêiner"
        float fps_real "US-01 RN02 — fps medido pelos carimbos de tempo dos quadros"
        bool fps_is_variable "US-01 RN03"
        int frame_count
        float duration_s
        datetime loaded_at "US-01 — quando a carga do vídeo foi feita"
        string trajectory_path "caminho do .parquet de pose/eventos gerado para o trial"
    }
    TRIAL_RESULT {
        int id PK
        int trial_id FK, UK
        float distance_cm
        float speed_mean_cm
        float speed_max_cm
        float path_tortuosity
        float primary_latency_s "tempo até 1ª visita ao target"
        float total_latency_s "tempo até entrar na escape box (nulo na probe)"
        int primary_errors "buracos errados antes do 1º acerto"
        int total_errors "buracos errados no trial inteiro"
        string search_strategy "random|serial|spatial"
        string heatmap_path
        string cox_test
        bool event_ocurred
        datetime calculated_at "US-02 — quando as métricas foram calculadas"
        float px_per_10cm_used "US-02 RN05 — escala usada; obsoleta se != maze_configs.px_per_10cm"
        float route_efficiency "US-02 RN03 — caminho ideal / caminho percorrido"
    }
    HOLE_VISIT {
        int id PK
        int trial_result_id FK
        int hole_id FK
        int visit_order "1,2,3... ordem cronológica no trial"
        float discovered_at_s "US-11 — descoberta (D), critério de percepção C1"
        float entered_at_s "US-13 — entrada (E), critério físico C2, tempo desde início do trial"
        float duration_s "quanto tempo o focinho ficou no buraco"
    }
```

<!--
Pontos identificados na revisão do schema mas propositalmente adiados —
retomar quando os cards correspondentes forem abertos:

- US-27 (proveniência completa das execuções): TRIAL_RESULT ainda não versiona
  qual modelo de pose, qual versão de config (`versao_definicoes` do
  configs/default.yaml) nem qual versão do pipeline gerou o resultado.
  Considerar `pose_model_version`, `config_version`, `processed_at`.
- US-20 (classificação de estratégia): TRIAL_RESULT não tem campo de entropia
  espacial da trajetória, usada como critério ("entropia_max_espacial").
- US-19 (índice de eficiência de rota): resolvido pela US-02 — `path_tortuosity`
  fica para outra métrica; `route_efficiency` (caminho-ideal / caminho-real)
  é campo próprio, adicionado em `0002_us02_calibration.sql`.
- US-21 / US-29 (kappa entre classificação automática e observador humano):
  falta onde guardar o rótulo manual de estratégia para comparar contra o
  `search_strategy` automático.
- US-18 (velocidade por fase): hoje só há `speed_mean_cm`/`speed_max_cm`
  agregados do trial inteiro; falta quebra por fase S→D vs. D→E.
-->


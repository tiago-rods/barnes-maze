# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Python offline pipeline that quantifies spatial learning in the Barnes
maze from top-down trial video: it extracts trajectory, per-hole events
(discovery vs. entry), and search-strategy classification. Client: LNBio.
The software delivers **data**; survival-analysis statistics stay in the
client's own `barnes_maze.py`. The bridge is an export compatible with the
lab's `trials.csv`/`probes.csv` (US-25).

Full scope, the 30-card backlog, sprints and acceptance criteria live in
`docs/CARDS.md` — read the relevant card before implementing a `US-NN`
feature; `docs/revisao-cards.md` records team decisions that **narrow**
those cards (e.g. MP4-only support for US-01, Postgres over SQLite).
`docs/DER.md` is the Postgres ER diagram (Mermaid) the schema is derived
from — update it whenever `database/migrations/` changes.
`docs/ROTEIRO-DEMONSTRACAO.md` is the PowerShell end-to-end script for the
client demo (US-01..US-06, on a separate `barnes_demo` database); the team
also uses it as the manual acceptance run. Whenever a `barnes` command's
options, messages or behavior change, update the matching step there too —
it breaks silently otherwise.

## Commands

Package manager is `uv`, not pip. On Windows, if `uv sync` fails with a TLS
certificate error, add `--native-tls`.

```bash
uv sync                              # install deps
uv sync --locked --extra pose        # SLEAP-NN 0.3.1/PyTorch cu128; docs/pose-treino-avaliacao.md
uv sync --extra anotacao             # + sleap-io, reads SLEAP .slp files, no CUDA (US-06)
    # NB: sleap-io 0.9.x's wheel installs its own top-level `tests` package into
    # site-packages, which shadows this repo's `tests/` (no __init__.py) for any
    # `import tests.…` outside pytest. pytest is unaffected (--import-mode=importlib);
    # scripts needing a test helper must put the folder on sys.path instead
    # (e.g. `sys.path.insert(0, 'tests/io'); from test_trim import …`).
uv sync --extra longitudinal         # + DTW/Fréchet (US-24)
    # NB: `uv sync` makes .venv match exactly the requested extras and UNINSTALLS
    # the others — a bare `uv sync` removes sleap-io/torch already installed.
    # Always pass every extra the machine uses in ONE command
    # (e.g. `uv sync --extra anotacao --extra pose`); check before syncing someone's env.

uv run pytest                        # full suite
uv run pytest tests/io/test_video.py -v   # single file
uv run pytest tests/db/ -v           # DB integration tests — see below

uv run ruff check src/ tests/        # lint (line-length 100, py311 target)

uv run barnes video load PATH [--experiment-id N --maze-config-id N \
    --phase acquisition --day 1 --trial-in-day 1 --rotation-deg 0] [--no-preview]
uv run barnes trial set-rotation ID DEG   # US-05; negatives need `--` first
uv run barnes trial show ID          # target hole in platform + room frames
uv run barnes db migrate             # apply pending database/migrations/*.sql

uv run barnes maze create --experiment-id N --name NAME \
    --reference-frame PATH --arena-diameter-cm X --hole-diameter-cm Y
    # interactive OpenCV window: drag center -> physical reference hole =
    # center/radius/angle (that hole becomes hole 0), right-click =
    # mark target hole, 'a' = auto-detect platform circle, +/- = N (max 30),
    # [ ] = hole radius (0.5 px steps; base of proximity zones, US-04 RN06);
    # --no-interactive requires --center-x/--center-y/--platform-radius-px
uv run barnes maze show ID           # reapply a saved montagem, no interaction

# US-02 (px->cm scale; stored on the maze_configs row itself, see Database
# schema below — --maze-config-id, not a separate camera/orientation entity)
uv run barnes scale calibrate --video PATH --maze-config-id N [--length-1-cm X --length-2-cm Y]
uv run barnes scale verify --video PATH --maze-config-id N [--length-cm Z]   # error must be < 3%
uv run barnes scale show --maze-config-id N
uv run barnes metrics process --video PATH --trajectory CSV --trial N   # montagem + interval from the trial

# US-06 (pose annotation set; files under data/annotations/, nothing in the DB)
uv run barnes pose sample --video PATH --maze-config-id N [--start-frame F --end-frame F] [--overwrite]
uv run barnes pose import-slp FILE.slp [FILE2.slp ...]   # -> data/annotations/anotacoes.csv
uv run barnes pose split                 # by trial -> data/annotations/divisao.csv
uv run barnes pose check-split           # fails naming any trial in >1 set
uv run barnes pose report [--maze-config-id N]   # per-trial montagem from amostragem.csv
uv run barnes metrics executions [--trial N [--history]]

# US-09/US-10 (pose series -> trajectory parquet; review of flagged pose gaps)
uv run barnes pose series --trial N --inference DIR   # + smoothing, short-gap interpolation, coverage
uv run barnes pose review --trial N [--video PATH] [--todos] [--margem 10]
    # OpenCV window opened directly at the first pending flagged segment:
    # n/p segment, a/d frame, 1/2/3 point, click = mark, right/Backspace = undo,
    # Enter = segment reviewed, s = save, Esc/x = cancel (nothing saved)

# US-18 (distance + mean speed from the trajectory parquet; no video)
uv run barnes metrics displacement --trial N [--ponto centro_corpo]
uv run barnes metrics distance-validate [--manual CSV] [--saida DIR]   # r >= 0.95; no CSV = blocked

# US-27 (provenance + catalog)
uv run barnes execution show ID      # model, thresholds, params, commit, dirty, "reproduzivel"
uv run barnes catalog list [--experiment-id N] [--verificar-hash] [--procurar-em DIR] [--json]
```

### Local Postgres for development

```bash
cp .env.example .env                 # once; .env is gitignored (holds the DSN)
docker compose up -d                 # Postgres 16 on port 5433 (BARNES_PG_PORT)
uv run barnes db migrate             # dev DB `barnes`
uv run barnes db migrate --dsn postgresql://barnes:barnes@localhost:5433/barnes_test
```

Port 5433, not 5432, so it never collides with a native PostgreSQL on the
dev machine. `database/docker-init/` creates the extra `barnes_test` DB on
first volume creation. `get_connection()` loads `.env` via python-dotenv
without overriding variables already set in the shell. It adds
`connect_timeout=10` unless the DSN sets its own (without it, a port with
nothing listening hangs the command forever on Windows) and turns a failed
connect into `DatabaseUnavailableError` — host/port/dbname only, never the
password; it subclasses both `DatabaseConfigError` (clean CLI message) and
`psycopg.OperationalError` (callers that already handle "database down" keep
working).

Tests never use the dev DB: `tests/conftest.py` overwrites
`BARNES_DATABASE_URL` with `BARNES_TEST_DATABASE_URL` (or with an empty string
when unset — empty, not deleted, so `.env` can't refill it) **before
collection**. Tests in `tests/db/` and `tests/test_cli.py` auto-`skip` (via
`pytestmark`) when it is empty, so `uv run pytest` works with or without a
database available. `tests/io/` and other unit tests never need a database
— video-reading logic is deliberately free of any DB dependency (see
Architecture below).

## Architecture

### Module boundary: `io` computes, `db` persists, CLI is the only thing that knows both

`src/barnes/io/video.py` reads a video and returns a `VideoMetadata`
dataclass (resolution, measured fps, duration, content hash, etc.). It has
**no** dependency on `psycopg` or on any experiment/trial context — it
can't know `experiment_id`/`maze_config_id` because those aren't derivable
from the file. `src/barnes/db/trials.py` maps a `VideoMetadata` plus that
external context onto a `trials` row. Only `src/barnes/cli.py` imports both
and wires them together. Keep this split when adding new pipeline stages
(pose, events, metrics, ...): compute in `io`/the stage's own module, persist
in `db`, orchestrate in `cli.py`.

Repository functions in `src/barnes/db/*.py` (e.g. `insert_trial`) do **not**
call `conn.commit()` — the caller controls the transaction boundary (the CLI
relies on `with get_connection(...) as conn:` auto-committing on clean exit
per psycopg3 semantics). `src/barnes/db/connection.py`'s `apply_migrations`
is the one exception: migrations must actually persist, so each migration
file is applied and committed in its own transaction and recorded in a
`schema_migrations` tracking table (idempotent — safe to re-run).

### Database schema

`database/migrations/NNNN_description.sql` — numbered, applied in order,
**never edit an already-applied migration**; add a new numbered file
instead. Schema mirrors `docs/DER.md`: `users → experiments → subjects`
(1 experiment = 1 subject, no reuse across experiments) and
`experiments → maze_configs` / `→ trials`. `maze_configs → holes`.
`trials → trial_results → hole_visits`, `trials → evento_buraco`,
`trials → correcao_pose` (US-10), and every
`trial_results`/`evento_buraco`/`correcao_pose` row → `execucao` (US-27, see below). Ownership chain uses
`ON DELETE CASCADE` throughout (deleting an experiment wipes everything
under it) — deliberate, not an oversight. Enumerated fields (`phase`,
`search_strategy`) and range fields (`angle_deg`) have `CHECK` constraints;
"measured" business thresholds (e.g. calibration error < 3%) are validated
by the application, not the database. `trials.content_hash` is `UNIQUE` —
a trial is identified by file content, not by path, so the same recording
can't be loaded twice under a different name (see US-01/US-27 below).
`trials.rotation_deg` (US-05, migration `0004`) is nullable with **no
DEFAULT** on purpose: NULL means "not registered" and longitudinal
analysis must refuse the trial, never assume 0°. Migration numbering has a
historical duplicate (`0002_trial_interval_manual_flag` and
`0002_us02_calibration`) — harmless because `schema_migrations` tracks by
filename; don't rename them (already-migrated DBs would re-apply), just keep
numbering forward. Pixel coordinates/radii (`maze_configs.center_*_px`,
`holes.x_px/y_px/radius_px`) are DOUBLE PRECISION since `0005` (were INTEGER).

The US-03 useful interval is persisted on the trial **and read back**:
`db.trials.get_trial` rebuilds it (via `io.trim.interval_from_seconds`, the
single seconds→frame conversion), and `metrics.process_trial` takes it as a
**required** argument and drops samples outside it (RN02). Trajectory
`time_s` is seconds from the start of the video file. `metrics process`
takes the montagem from the trial itself, never from a free
`--maze-config-id`. Any new pipeline stage must do the same: read the trial,
apply its interval upstream.

### Reference frames (US-05)

`src/barnes/geometry/reference_frame.py` converts between three angular
frames, all sharing `holes.py`'s convention (0° = +x, clockwise on screen):
image (`holes.angle_deg`, camera-dependent), platform (`hole_number`) and
room (`(k·360/N + rotation) mod 360`). Hole 0 of **every** montagem must be
the lab's agreed **physical reference hole** — the camera only sees the
platform from above (no wall landmark), and the platform doesn't rotate
(B4), so that hole anchors the room frame. A moved camera means a new
`maze_configs` row dragged to the same physical hole; room angles stay
comparable across montagens. Any analysis comparing trials (US-24, US-26,
cross-trial visit sequences) must work in the room frame and go through
`require_rotations()` first, which raises `MissingRotationError` listing
every trial without rotation. Output columns carrying a position must end
in `ReferenceFrame` suffixes (`_image`/`_platform`/`_room`, RN05).

US-02's px->cm scale (`maze_configs.px_per_10cm`/`calibration_date`/
`measured_error_pct`/`calibration_segments`/`calibration_reference_*`) and
its RN05 "recalibrating invalidates old results" rule
(`trial_results.calculated_at`/`px_per_10cm_used`) are both columns added by
later migrations on the already-existing tables, not a new entity. Since
US-27 (`0007`) `trial_results` is **one row per trial per execution**
(`UNIQUE(execucao_id)`, no longer `UNIQUE(trial_id)`): reprocessing appends;
"current" = most recent row (`get_trial_result`), full history via
`list_trial_result_history`. Staleness is derived when read (`calculated_at`/`px_per_10cm_used` vs. the
montagem's current values), never stored as a boolean — same philosophy as
`measured_error_pct` above. See `src/barnes/db/calibration.py` and
`src/barnes/db/trial_results.py`.

### Video metadata quirk (US-01)

`is_fps_variable()` compares each inter-frame interval to the **mean**
interval (`1 / fps_real`) with a **25%** tolerance — not 1%. Real LNBio
footage showed B-frame reordering producing a legitimate, structural
~32ms/~48ms alternating pattern (still averaging to a constant 25fps); the
original 1%-of-mean check flagged essentially every real video as "variable
fps", which defeats the point of the warning. A later **median** reference
was also wrong: with almost half of each value, the median lands on 32 or
48 ms depending on which group is a few intervals larger, and the whole other
group exceeds 25% (false positive on the full 6-min LNBio video of
23/06/2020). Against the mean, the pattern deviates ~20% whatever the balance.
Don't change this without re-testing against real (not synthetic) footage —
synthetic test videos written via `cv2.VideoWriter` don't reproduce this
jitter, which is why `tests/io/test_video.py` has dedicated regression tests
for the balanced and unbalanced alternating pattern.

### Configuration is data, not code

`configs/default.yaml` (behavioral thresholds: discovery distance/angle,
dwell, error criteria, strategy classification) is intentionally versioned
YAML, meant to be populated from the lab via gate **G3** (see
`docs/definicoes-metricas.md`, DRAFT/unsigned) and calibrated against manual
annotation, never hardcoded or guessed. **Contact with the lab never happened**:
on 2026-11-12 the team approved its own values, each justified in
`docs/decisoes-sem-laboratorio.md` and filled in with
`versao_definicoes: decisoes-equipe-2026-11-12-sem-G3` (copied into every
`execucao.limiares`). G3 stays open and the report declares it. Don't change a
threshold "reasonably" outside that document — a value chosen for convenience
produces plausible, well-formatted numbers with no relationship to what the lab
means by e.g. "discovery latency". The US-25 export follows the schema the lab's
`barnes_maze.py` (outside the repo, in the parent folder) actually reads —
including **distances in metres**, while every metric is computed in cm.

Per-rig geometry/camera calibration (center, radius, N holes, target hole,
px→cm scale) used to live in `configs/montagens/*.yaml`; US-04 moved it to
Postgres instead (`maze_configs` + `holes`, see Database schema below) —
`configs/montagens/` now holds only a README pointing here, no YAML.
Configure a montagem with `barnes maze create` and reload it with
`barnes maze show <id>`; never hand-edit geometry into a file.

The `anotacao:` section (US-06) and the `pose:` section (US-10) are the
deliberate exceptions to "null until G3": their values are parameters owned by
the team, not lab metric thresholds. `anotacao:` holds the **annotation protocol**
(which frames get sampled, region boundaries, split proportions, seed), read
via `barnes.pose.protocol` and documented in `docs/protocolo-anotacao.md`.
`pose:` holds the **pose-quality treatment** (minimum coverage, short-gap limit,
smoothing window), read via `barnes.pose.quality.load_quality_params` and
documented in `docs/contrato-trajetoria.md` ("Pós-processamento") and
`docs/revisao-cards.md`. Keep each section in sync with its doc.

### Seed scripts live outside the installed package

`database/seeds/*.py` (e.g. `lnbio_barnes.py`) import `barnes.db`/
`barnes.geometry` but are not part of `src/barnes` — the installed `barnes`
console script does not have the repo root on `sys.path`, so these only run
via `uv run python -m database.seeds.<name>` from the repo root, never as a
`barnes` subcommand.

### Package layout

`src/barnes/{io,geometry,pose,events,metrics,strategy,longitudinal,stats,report,db}/`
— each corresponds to both a project epic and a pipeline stage. `io`
(US-01), `geometry` (US-04, plus US-05 reference frames) and
`io/calibration.py`/`metrics` (US-02, scale and the
distance/speed/route-efficiency conversions it gates) are implemented;
`pose` includes US-06 annotation plus US-07 dataset/training, US-08
evaluation/offline inference, US-09 series and US-10 quality/review.
`cli_pose.py` orchestrates the US-07/08 commands (`pose series`/`pose review`
live in `cli.py`);
`db/pose_executions.py` records immutable `execucao` rows (migration 0006).

US-09 trajectory (`pose/series.py` + `pose/trajectory.py`): `barnes pose series`
turns an inference run's `pose.csv` (pixels, `time_s` from video start) into
`data/interim/trial_<id>.parquet` — the input contract of the whole Epic D
(events), US-10 and metrics. The schema is a fixed `pyarrow.Schema` checked
**on write and on read** (`TrajectoryContractError`); `docs/contrato-trajetoria.md`
is its human copy — change both together and bump `CONTRACT_VERSION` on any
incompatible change. Missing pose is NaN + `*_valido=false`, never forward-filled.
θ (`theta_deg_image`) =
`atan2(dy, dx)` centro→focinho in image axes = `holes.angle_deg` convention.
Positions are cm in image axes (`_image`, origin top-left). `t_s` is from the
useful-interval start. With stdout/stderr redirected (file or pipe), Windows
Python writes cp1252 and Typer/Rich crashed on characters like θ or → in a
command's help. The console script is therefore `barnes.cli:main`, not the Typer
`app`: `main()` calls `ensure_utf8_output()` (reconfigures non-UTF-8 streams to
UTF-8) before `app()`. Keep it as the entry point; regression test in
`tests/test_cli_encoding.py`.

US-10 pose quality (`pose/quality.py`, pure, in **pixels** before `build_series`):
`pose series` builds the series as a pure function of the inference's `pose.csv`
+ every manual correction of the trial (`correcao_pose`) + the `pose:` config, in
the fixed order corrections → median smoothing (within present runs, symmetric
shrinking window) → linear interpolation of short interior gaps (per point;
`interpolado = true`) → flag remaining long/edge gaps → coverage (three points,
interpolated and corrected frames count). Never smooth an already-written series:
regenerate from `pose.csv` (that is why the review re-runs the same path,
`_load_series_inputs`/`_write_series` in `cli.py`). The quality report goes to the
Parquet metadata `pos_processamento` (a row with `interpolado` without it is a
contract error) and to `execucao.metadata.qualidade_pose`; coverage to
`trials.cobertura_pose`. `pose review` (`pose/review_ui.py`: pure `ReviewSession`
+ thin cv2 loop, like `io/calibration_ui.py`) writes corrections + the new series
+ coverage under one `execucao` with `parametros.comando = 'pose review'`
(`trechos_revisados` there un-pend segments). The quality mark (RN06) is
**derived** by the VIEW `qualidade_pose` (0008), never stored as a flag; catalog
and `trial_results` reads join it, and any new output (US-25) must too. Code that
needs the exact frame at an index must use `io.video.iter_frames` (sequential, no
seek), never `read_frame` (seek) — see the B-frames note below.

US-27 provenance (`0007`): every stage that writes results must first write
an `execucao` row — `kind='processamento'` via
`db/executions.record_processing_execution` — **in the same transaction** as
its metrics/events. `trial_results.execucao_id` and `evento_buraco.execucao_id`
are `NOT NULL` with a composite FK `(execucao_id, trial_id) → execucao(id,
trial_id)`, so an orphan or cross-trial metric is a schema error, not a
convention. Commit/dirty has a single implementation,
`pose.dataset.git_revision_record` (US-07/08) — wrap its dict with
`provenance.GitState.from_record`; thresholds via
`provenance.thresholds_snapshot`; file hashes via `pose.dataset.file_sha256`.
Don't add another git/hash helper. Dirty includes untracked files, and "no
git" is `None`, never clean. Before reprocessing,
check the video with `io.video.verify_video_file` against
`trials.content_hash` (refuse `alterado`, warn and record on `movido`).
`db/catalog.list_catalog` is the UI-agnostic catalog; its `situacao` is
derived on read (`trials.status` from 0001 is unused). Card table names map to
existing tables (animal=`subjects`, montagem=`maze_configs`,
metrica=`trial_results`, sessao=VIEW `sessao`) — see `docs/DER.md`.
`execucao` is immutable by trigger; `0007` disables it only inside its own
backfill transaction.
Production training requires NVIDIA; ordinary unit tests need no GPU.
Native backend smoke tests use synthetic data and do not attest lab quality.
`events/discovery.py` implements US-11 and is not changed by threshold calibration.
US-12/13 live in `events/calibration.py`, `events/entry.py`, and `cli_events.py`:
manual D3 comparisons append rounds, entry events include confirmation time and
D-to-E path length. Numeric C2 parameters are team decisions (raio_fator 1.0, 0.2 s), not lab-calibrated.
`evento_buraco.details` (0009) stores entry evidence; processing and events share
one transaction. Recalculation reads the trajectory and its provenance without
opening the video. See `docs/eventos-calibracao-entrada.md` for time conventions
and actual acceptance blockers. `strategy`/`longitudinal`/`stats`/`report` remain
empty `__init__.py` stubs pending their user story.

US-18 (`metrics/displacement.py`, `metrics/validation.py`, `cli_metrics.py`): one
distance and one mean speed per trial from the US-09 parquet (narrowed card: no
per-phase speeds — the lab's `barnes_maze.py` derives those from trials.csv). Reuses
US-16's `travelled_distance_cm` (gaps bridged in a straight line, `centro_corpo`); speed
divides by first→last valid sample, not the whole interval. `cli_metrics` loads the
series through `cli_events.load_trajectory_inputs` (same identity/scale/fps/interval
checks as events). `trial_results.interpolated_fraction` (0010) is stored; the
variable-fps speed caveat is **derived** from `trials.fps_is_variable` on read, never
stored. US-25 complementary columns: `path_distance`, `mean_speed`,
`interpolated_fraction`, `speed_time_base_approx` (`Displacement.as_export_columns`).
The r >= 0.95 acceptance is blocked until a manual reference exists
(`docs/definicoes-metricas.md` §4.3).

US-28 (`tests/test_us28_trial_referencia.py`): regression test over a versioned
**synthetic** video (`tests/fixtures/trial_referencia.mp4`) with a known trajectory
injected as `PoseFrames` → `build_series`; expected values (abs. tolerance 1e-6) and
its own thresholds live in `tests/fixtures/trial_referencia_esperado.yaml`, decoupled
from `configs/default.yaml`. When a story adds a metric (US-19..22 next), add it to
the expected YAML; changing an existing expected value needs a justification in the
commit message (RN04). It must pass before merging to the main branch — a review
rule, there is no CI. The fixture has no pose gaps, no censoring and constant fps.

`pose/` notes (US-06): the internal annotation format (`anotacoes.csv`) is
tool-agnostic and `annotations.from_slp` is the only SLEAP-aware code, because
RN07 may still swap SLEAP for YOLO-pose. Trials are keyed by
`trial_key(content_hash)` (first 12 hex chars), same identity rule as
`trials.content_hash`, so a renamed copy can't leak across train/test.
`pose/regions.py` (centro/borda/buraco) is meant to be reused by US-08's
per-region error report. Region during *sampling* comes from contrast
segmentation (no model exists yet); the *reported* count uses the annotated
`centro_corpo`, classified with each trial's **own** montagem (`maze_config_id`
recorded in `<trial>/amostragem.csv` by `pose sample`) — never one montagem for
all trials, since the camera can shift between recording days. `from_slp`
rejects `.pkg.slp` (embedded images): its "video" is the .slp itself, which
would turn into a fake trial key and defeat the leakage check. Sampling scan
and PNG export both decode **sequentially from frame 0** (`io.video.iter_frames`), never
via `CAP_PROP_POS_FRAMES` seek — with LNBio's B-frames a seek can land on a
neighbor frame, so the exported PNG/`quadro` index wouldn't be the frame whose
region was estimated. Re-sampling a trial refuses to touch existing PNGs
(possibly already annotated) unless `--overwrite`. `data/` and
`models/` are gitignored (raw videos, trained pose weights) — never assume
their contents are present in a fresh clone or CI; tests must not depend on
files under `data/`, which is why `tests/conftest.py` generates small
synthetic `.mp4` fixtures via `cv2.VideoWriter` instead.

## Conventions

- Google-style docstrings, type hints, `pathlib.Path` over raw strings,
  frozen `@dataclass` for value objects, domain-specific exceptions
  (`VideoLoadError`, `DatabaseConfigError`, `GeometryValidationError`)
  instead of bare `Exception`.
- No GPL/AGPL dependencies anywhere in the main dependency group — this is
  an explicit distribution constraint (see comments in `pyproject.toml`).
  This is why `scipy`/`scikit-learn` are used instead of `pingouin` (GPL-3),
  and why adopting YOLO-pose (AGPL) instead of SLEAP would need to be the
  client's decision, not the team's.

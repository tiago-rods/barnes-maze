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

## Commands

Package manager is `uv`, not pip. On Windows, if `uv sync` fails with a TLS
certificate error, add `--native-tls`.

```bash
uv sync                              # install deps
uv sync --extra pose                 # + SLEAP (read pyproject.toml warning first)
uv sync --extra longitudinal         # + DTW/Fréchet (US-24)

uv run pytest                        # full suite
uv run pytest tests/io/test_video.py -v   # single file
uv run pytest tests/db/ -v           # DB integration tests — see below

uv run ruff check src/ tests/        # lint (line-length 100, py311 target)

uv run barnes video load PATH [--experiment-id N --maze-config-id N \
    --phase acquisition --day 1 --trial-in-day 1] [--no-preview]
uv run barnes db migrate             # apply pending database/migrations/*.sql

uv run barnes maze create --experiment-id N --name NAME \
    --reference-frame PATH --arena-diameter-cm X --hole-diameter-cm Y
    # interactive OpenCV window: drag = center/radius/angle, right-click =
    # mark target hole, 'a' = auto-detect platform circle, +/- = N (max 30);
    # --no-interactive requires --center-x/--center-y/--platform-radius-px
uv run barnes maze show ID           # reapply a saved montagem, no interaction

# US-02 (px→cm scale per camera orientation; still on its own SQLite/Postgres
# repository via --database/BARNES_DATABASE — pending unification with db/)
uv run barnes scale calibrate --video PATH --orientation ID [--length-1-cm X --length-2-cm Y]
uv run barnes scale verify --video PATH --orientation ID [--length-cm Z]   # error must be < 3%
uv run barnes scale show --orientation ID [--history]
uv run barnes metrics process --video PATH --trajectory CSV --trial ID --orientation ID
uv run barnes metrics executions [--trial ID]
```

### Local Postgres for development

```bash
docker compose up -d
export BARNES_DATABASE_URL="postgresql://barnes:barnes@localhost:5432/barnes"
uv run barnes db migrate
```

Tests in `tests/db/` are integration tests against a real Postgres with the
schema applied; they auto-`skip` (via `pytestmark`) when
`BARNES_DATABASE_URL` is unset, so `uv run pytest` works with or without a
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
`trials → trial_results → hole_visits`. Ownership chain uses
`ON DELETE CASCADE` throughout (deleting an experiment wipes everything
under it) — deliberate, not an oversight. Enumerated fields (`phase`,
`search_strategy`) and range fields (`angle_deg`) have `CHECK` constraints;
"measured" business thresholds (e.g. calibration error < 3%) are validated
by the application, not the database. `trials.content_hash` is `UNIQUE` —
a trial is identified by file content, not by path, so the same recording
can't be loaded twice under a different name (see US-01/US-27 below).

### Video metadata quirk (US-01)

`is_fps_variable()` compares each inter-frame interval to the **median**
(not mean) with a **25%** tolerance — not 1%. Real LNBio footage showed
B-frame reordering producing a legitimate, structural ~32ms/~48ms
alternating pattern (still averaging to a constant 25fps); the original
1%-of-mean check flagged essentially every real video as "variable fps",
which defeats the point of the warning. Don't tighten this without
re-testing against real (not synthetic) footage — synthetic test videos
written via `cv2.VideoWriter` don't reproduce this jitter, which is why
`tests/io/test_video.py` has a dedicated regression test for the alternating
pattern alongside the synthetic-video tests.

### Configuration is data, not code

`configs/default.yaml` (behavioral thresholds: discovery distance/angle,
dwell, error criteria, strategy classification) is intentionally versioned
YAML with most values `null` — populated from the lab via gate **G3** (see
`docs/definicoes-metricas.md`, currently DRAFT/unsigned) and calibrated
against manual annotation, never hardcoded or guessed. Don't fill it in
"reasonably" — a value chosen for convenience produces plausible,
well-formatted numbers with no relationship to what the lab actually means
by e.g. "discovery latency".

Per-rig geometry/camera calibration (center, radius, N holes, target hole,
px→cm scale) used to live in `configs/montagens/*.yaml`; US-04 moved it to
Postgres instead (`maze_configs` + `holes`, see Database schema below) —
`configs/montagens/` now holds only a README pointing here, no YAML.
Configure a montagem with `barnes maze create` and reload it with
`barnes maze show <id>`; never hand-edit geometry into a file.

### Seed scripts live outside the installed package

`database/seeds/*.py` (e.g. `lnbio_barnes.py`) import `barnes.db`/
`barnes.geometry` but are not part of `src/barnes` — the installed `barnes`
console script does not have the repo root on `sys.path`, so these only run
via `uv run python -m database.seeds.<name>` from the repo root, never as a
`barnes` subcommand.

### Package layout

`src/barnes/{io,geometry,pose,events,metrics,strategy,longitudinal,stats,report,db}/`
— each corresponds to both a project epic and a pipeline stage. `io`
(US-01) and `geometry` (US-04) are implemented; the rest are still empty
`__init__.py` stubs pending their user story. `data/` and
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

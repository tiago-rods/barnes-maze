# GERADO por scripts/gerar_roteiro_ps1.py a partir de docs/ROTEIRO-DEMONSTRACAO.md.
# Não edite à mão: mude o roteiro e gere de novo.
#
# Uso (PowerShell, da raiz do repositório barnes-maze):
#   powershell -ExecutionPolicy Bypass -File scripts\roteiro-demonstracao.ps1
#   ... -PausarEntrePassos   para parar a cada seção (bom para apresentar)
#
# Roda do começo ao fim: cada seção depende das variáveis das anteriores.
# Antes, faça commit de tudo e confira os caminhos dos vídeos na A.3.
param([switch]$PausarEntrePassos)
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Titulo([string]$id, [string]$texto) {
    Write-Host ''
    Write-Host ('=' * 78) -ForegroundColor Cyan
    Write-Host ($id + '  ' + $texto) -ForegroundColor Cyan
    Write-Host ('=' * 78) -ForegroundColor Cyan
}
function Mostrar([string[]]$linhas) {
    foreach ($l in $linhas) { Write-Host ('PS> ' + $l) -ForegroundColor DarkGray }
}
function Janela([string]$dica) {
    Write-Host ''
    Write-Host ('ABRE JANELA - ' + $dica) -ForegroundColor Yellow
    Read-Host 'Enter para abrir a janela' | Out-Null
}
function Pausa {
    if ($PausarEntrePassos) { Read-Host 'Enter para continuar' | Out-Null }
}

Titulo 'A.1' 'Ambiente'
# pulado (o script já roda na pasta do repositório): cd barnes-maze
Mostrar @('git status --short')
git status --short
Mostrar @('docker compose up -d')
docker compose up -d
Mostrar @('uv sync --system-certs --extra anotacao')
uv sync --system-certs --extra anotacao
Pausa

Titulo 'A.2' 'Banco de demonstração limpo'
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes -c "DROP DATABASE IF EXISTS barnes_demo"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes -c "DROP DATABASE IF EXISTS barnes_demo"
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes -c "CREATE DATABASE barnes_demo"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes -c "CREATE DATABASE barnes_demo"
Mostrar @('$env:BARNES_DATABASE_URL = "postgresql://barnes:barnes@localhost:5433/barnes_demo"')
$env:BARNES_DATABASE_URL = "postgresql://barnes:barnes@localhost:5433/barnes_demo"
Mostrar @('uv run barnes db migrate')
uv run barnes db migrate
Mostrar @('uv run barnes db migrate --dsn postgresql://barnes:barnes@localhost:5433/barnes_test')
uv run barnes db migrate --dsn postgresql://barnes:barnes@localhost:5433/barnes_test
Mostrar @('$env:BARNES_TEST_DATABASE_URL = "postgresql://barnes:barnes@localhost:5433/barnes_test"')
$env:BARNES_TEST_DATABASE_URL = "postgresql://barnes:barnes@localhost:5433/barnes_test"
Mostrar @('Remove-Item -Recurse -Force data\demo_anotacao, data\pose\demo, data\demo_interim, data\demo_events, data\demo_validation -ErrorAction SilentlyContinue')
Remove-Item -Recurse -Force data\demo_anotacao, data\pose\demo, data\demo_interim, data\demo_events, data\demo_validation -ErrorAction SilentlyContinue
Pausa

Titulo 'A.3' 'Arquivos usados na demonstração'
Mostrar @('$v1 = "data\raw\barnes-sample-1.mp4"')
$v1 = "data\raw\barnes-sample-1.mp4"
Mostrar @('$v2 = "data\raw\barnes-sample-2.mp4"')
$v2 = "data\raw\barnes-sample-2.mp4"
Mostrar @('$vc = "data\raw\BM_Animal_1_Aquisicao_trial_2_23.06.2020.mp4"')
$vc = "data\raw\BM_Animal_1_Aquisicao_trial_2_23.06.2020.mp4"
Mostrar @('uv run python -c "import sys; sys.path.insert(0, ''tests/io''); from pathlib import Path; from test_trim import _write_release_video; _write_release_video(Path(''data/raw/sintetico_soltura.mp4''))"')
uv run python -c "import sys; sys.path.insert(0, 'tests/io'); from pathlib import Path; from test_trim import _write_release_video; _write_release_video(Path('data/raw/sintetico_soltura.mp4'))"
Mostrar @('$vs = "data\raw\sintetico_soltura.mp4"')
$vs = "data\raw\sintetico_soltura.mp4"
Mostrar @('Set-Content -Path data\raw\corrompido.mp4 -Value "isto nao e um video" -Encoding utf8')
Set-Content -Path data\raw\corrompido.mp4 -Value "isto nao e um video" -Encoding utf8
Mostrar @('Set-Content -Path data\interim\traj_demo.csv -Value "x_px,y_px,time_s","10,10,0","40,50,2","70,90,4" -Encoding utf8')
Set-Content -Path data\interim\traj_demo.csv -Value "x_px,y_px,time_s","10,10,0","40,50,2","70,90,4" -Encoding utf8
Mostrar @('$anot = "data\demo_anotacao"')
$anot = "data\demo_anotacao"
Mostrar @('$posedemo = "data\pose\demo"')
$posedemo = "data\pose\demo"
Mostrar @('$interim = "data\demo_interim"')
$interim = "data\demo_interim"
Pausa

Titulo 'A.4' 'Medidas físicas do labirinto'
Mostrar @('$arena_cm = 92')
$arena_cm = 92
Mostrar @('$buraco_cm = 5')
$buraco_cm = 5
Pausa

Titulo 'B.1' 'Qualidade: testes automáticos e lint'
Mostrar @('uv run pytest -q')
uv run pytest -q
Mostrar @('uv run ruff check src/ tests/')
uv run ruff check src/ tests/
Pausa

Titulo 'B.2' 'Cadastro do experimento'
Mostrar @('$user = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "INSERT INTO users (email, name) VALUES (''demo@lnbio.local'', ''Demonstração'') RETURNING id").Trim()')
$user = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "INSERT INTO users (email, name) VALUES ('demo@lnbio.local', 'Demonstração') RETURNING id").Trim()
Mostrar @('$exp = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "INSERT INTO experiments (user_id, name) VALUES ($user, ''Experimento demonstração'') RETURNING id").Trim()')
$exp = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "INSERT INTO experiments (user_id, name) VALUES ($user, 'Experimento demonstração') RETURNING id").Trim()
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "INSERT INTO subjects (experiment_id, name) VALUES ($exp, ''Camundongo demo'')"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "INSERT INTO subjects (experiment_id, name) VALUES ($exp, 'Camundongo demo')"
Mostrar @('"usuário $user, experimento $exp"')
"usuário $user, experimento $exp"
Pausa

Titulo 'B.3' 'US-04 — Montagem paramétrica do labirinto'
Janela 'B.3: a = borda, h = buracos, arraste do centro ao buraco de referência, botão direito no alvo, +/- muda N, [ ] raio do buraco, Enter confirma (Esc e q também salvam).'
Mostrar @('uv run barnes maze create --experiment-id $exp --name "montagem demo" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm')
uv run barnes maze create --experiment-id $exp --name "montagem demo" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm
Mostrar @('$maze = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM maze_configs WHERE experiment_id = $exp AND name = ''montagem demo'' ORDER BY id DESC LIMIT 1").Trim()')
$maze = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM maze_configs WHERE experiment_id = $exp AND name = 'montagem demo' ORDER BY id DESC LIMIT 1").Trim()
Mostrar @('"montagem $maze"')
"montagem $maze"
Mostrar @('uv run barnes maze show $maze')
uv run barnes maze show $maze
Janela 'B.3: h acha o anel; arraste até o buraco escuro de cima à direita e marque o MESMO buraco como alvo (botão direito); Enter confirma.'
Mostrar @('uv run barnes maze create --experiment-id $exp --name "montagem completa" --reference-frame $vc --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm')
uv run barnes maze create --experiment-id $exp --name "montagem completa" --reference-frame $vc --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm
Mostrar @('$mazec = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM maze_configs WHERE experiment_id = $exp AND name = ''montagem completa'' ORDER BY id DESC LIMIT 1").Trim()')
$mazec = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM maze_configs WHERE experiment_id = $exp AND name = 'montagem completa' ORDER BY id DESC LIMIT 1").Trim()
Mostrar @('uv run barnes maze create --experiment-id $exp --name "invalida" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px 200 --hole-count 2')
uv run barnes maze create --experiment-id $exp --name "invalida" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px 200 --hole-count 2
Mostrar @('uv run barnes maze create --experiment-id $exp --name "invalida" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px -5')
uv run barnes maze create --experiment-id $exp --name "invalida" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px -5
Mostrar @('uv run barnes maze create --experiment-id $exp --name "invalida" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px 200 --target-hole-number 25')
uv run barnes maze create --experiment-id $exp --name "invalida" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px 200 --target-hole-number 25
Mostrar @('uv run pytest tests/geometry/test_holes.py tests/geometry/test_validation.py -v')
uv run pytest tests/geometry/test_holes.py tests/geometry/test_validation.py -v
Pausa

Titulo 'B.4' 'US-01 — Carga do vídeo e leitura dos metadados'
Janela 'B.4: a janela mostra o primeiro quadro: n avança, p volta, q fecha.'
Mostrar @('uv run barnes video load $v1')
uv run barnes video load $v1
Mostrar @('uv run barnes video load $vc --no-preview')
uv run barnes video load $vc --no-preview
Mostrar @('uv run pytest tests/io/test_video.py -v')
uv run pytest tests/io/test_video.py -v
Mostrar @('uv run barnes video load data\raw\nao_existe.mp4 --experiment-id $exp --maze-config-id $maze --no-preview')
uv run barnes video load data\raw\nao_existe.mp4 --experiment-id $exp --maze-config-id $maze --no-preview
Mostrar @('uv run barnes video load data\raw\video.avi --experiment-id $exp --maze-config-id $maze --no-preview')
uv run barnes video load data\raw\video.avi --experiment-id $exp --maze-config-id $maze --no-preview
Mostrar @('uv run barnes video load data\raw\corrompido.mp4 --experiment-id $exp --maze-config-id $maze --no-preview')
uv run barnes video load data\raw\corrompido.mp4 --experiment-id $exp --maze-config-id $maze --no-preview
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT count(*) AS trials FROM trials"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT count(*) AS trials FROM trials"
Pausa

Titulo 'B.5' 'US-02 — Calibração da escala px→cm'
Janela 'B.5/B.8: clique nas pontas de dois diâmetros da plataforma (4 cliques) e Enter. Botão direito desfaz, R recomeça.'
Mostrar @('uv run barnes scale calibrate --video $v1 --maze-config-id $maze --length-1-cm $arena_cm --length-2-cm $arena_cm')
uv run barnes scale calibrate --video $v1 --maze-config-id $maze --length-1-cm $arena_cm --length-2-cm $arena_cm
Janela 'B.5: marque um terceiro diâmetro, na diagonal (2 cliques), e Enter.'
Mostrar @('uv run barnes scale verify --video $v1 --maze-config-id $maze --length-cm $arena_cm')
uv run barnes scale verify --video $v1 --maze-config-id $maze --length-cm $arena_cm
Mostrar @('uv run barnes scale show --maze-config-id $maze')
uv run barnes scale show --maze-config-id $maze
Janela 'B.5: os mesmos 4 cliques, agora no vídeo completo, e Enter.'
Mostrar @('uv run barnes scale calibrate --video $vc --maze-config-id $mazec --length-1-cm $arena_cm --length-2-cm $arena_cm')
uv run barnes scale calibrate --video $vc --maze-config-id $mazec --length-1-cm $arena_cm --length-2-cm $arena_cm
Mostrar @('uv run pytest tests/io/test_calibration.py -v')
uv run pytest tests/io/test_calibration.py -v
Pausa

Titulo 'B.6' 'US-03 — Recorte do intervalo útil do trial'
Mostrar @('uv run barnes video load $vs --no-preview')
uv run barnes video load $vs --no-preview
Mostrar @('uv run barnes video load $vs --start-s 0.5 --end-s 2.0 --no-preview')
uv run barnes video load $vs --start-s 0.5 --end-s 2.0 --no-preview
Mostrar @('uv run barnes video load $vs --start-frame 3 --end-frame 20 --no-preview')
uv run barnes video load $vs --start-frame 3 --end-frame 20 --no-preview
Mostrar @('uv run barnes video load $vs --start-s 1 --start-frame 10 --no-preview')
uv run barnes video load $vs --start-s 1 --start-frame 10 --no-preview
Mostrar @('uv run barnes video load $vs --start-s 2 --end-s 1 --no-preview')
uv run barnes video load $vs --start-s 2 --end-s 1 --no-preview
Mostrar @('uv run barnes video load $vs --end-s 999 --no-preview')
uv run barnes video load $vs --end-s 999 --no-preview
Mostrar @('uv run barnes video load $v1 --experiment-id $exp --maze-config-id $maze --day 1 --trial-in-day 1 --no-preview')
uv run barnes video load $v1 --experiment-id $exp --maze-config-id $maze --day 1 --trial-in-day 1 --no-preview
Mostrar @('uv run barnes video load $v2 --experiment-id $exp --maze-config-id $maze --day 2 --trial-in-day 1 --start-s 2 --rotation-deg 90 --no-preview')
uv run barnes video load $v2 --experiment-id $exp --maze-config-id $maze --day 2 --trial-in-day 1 --start-s 2 --rotation-deg 90 --no-preview
Mostrar @('$t1 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $maze AND day_number = 1 ORDER BY id DESC LIMIT 1").Trim()')
$t1 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $maze AND day_number = 1 ORDER BY id DESC LIMIT 1").Trim()
Mostrar @('$t2 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $maze AND day_number = 2 ORDER BY id DESC LIMIT 1").Trim()')
$t2 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $maze AND day_number = 2 ORDER BY id DESC LIMIT 1").Trim()
Mostrar @('uv run barnes video load $vc --experiment-id $exp --maze-config-id $mazec --day 1 --trial-in-day 2 --start-s 81.5 --end-s 270 --no-preview')
uv run barnes video load $vc --experiment-id $exp --maze-config-id $mazec --day 1 --trial-in-day 2 --start-s 81.5 --end-s 270 --no-preview
Mostrar @('$tc = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $mazec ORDER BY id DESC LIMIT 1").Trim()')
$tc = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $mazec ORDER BY id DESC LIMIT 1").Trim()
Mostrar @('uv run barnes video load $v1 --experiment-id $exp --maze-config-id $maze --day 3 --no-preview')
uv run barnes video load $v1 --experiment-id $exp --maze-config-id $maze --day 3 --no-preview
Mostrar @('uv run barnes video load $v1 --experiment-id $exp --no-preview')
uv run barnes video load $v1 --experiment-id $exp --no-preview
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT id, filename, left(content_hash, 12) AS hash, day_number AS dia, rotation_deg AS rotacao, round(start_time_seconds::numeric,2) AS inicio_s, round(end_time_seconds::numeric,2) AS fim_s, interval_manually_adjusted AS ajuste_manual FROM trials ORDER BY id"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT id, filename, left(content_hash, 12) AS hash, day_number AS dia, rotation_deg AS rotacao, round(start_time_seconds::numeric,2) AS inicio_s, round(end_time_seconds::numeric,2) AS fim_s, interval_manually_adjusted AS ajuste_manual FROM trials ORDER BY id"
Mostrar @('uv run pytest tests/io/test_trim.py -v')
uv run pytest tests/io/test_trim.py -v
Pausa

Titulo 'B.7' 'US-05 — Rotação da plataforma e referencial da sala'
Mostrar @('uv run barnes trial show $t1')
uv run barnes trial show $t1
Mostrar @('uv run barnes trial show $t2')
uv run barnes trial show $t2
Mostrar @('uv run barnes trial set-rotation -- $t2 -90')
uv run barnes trial set-rotation -- $t2 -90
Mostrar @('uv run barnes trial show $t2')
uv run barnes trial show $t2
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "UPDATE trials SET rotation_deg = NULL WHERE id = $t2"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "UPDATE trials SET rotation_deg = NULL WHERE id = $t2"
Mostrar @('uv run barnes trial show $t2')
uv run barnes trial show $t2
Mostrar @('uv run barnes trial set-rotation $t2 90')
uv run barnes trial set-rotation $t2 90
Mostrar @('uv run pytest tests/geometry/test_reference_frame.py -v')
uv run pytest tests/geometry/test_reference_frame.py -v
Pausa

Titulo 'B.8' 'US-02 — Métricas em cm, bloqueio sem escala e recalibração'
Mostrar @('uv run barnes metrics process --video $v1 --trial $t1 --trajectory data\interim\traj_demo.csv')
uv run barnes metrics process --video $v1 --trial $t1 --trajectory data\interim\traj_demo.csv
Mostrar @('uv run barnes metrics executions --trial $t1')
uv run barnes metrics executions --trial $t1
Mostrar @('uv run barnes metrics process --video $v2 --trial $t2 --trajectory data\interim\traj_demo.csv')
uv run barnes metrics process --video $v2 --trial $t2 --trajectory data\interim\traj_demo.csv
Mostrar @('uv run barnes maze create --experiment-id $exp --name "montagem sem escala" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px 200')
uv run barnes maze create --experiment-id $exp --name "montagem sem escala" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px 200
Mostrar @('$maze0 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM maze_configs WHERE experiment_id = $exp AND name = ''montagem sem escala'' ORDER BY id DESC LIMIT 1").Trim()')
$maze0 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM maze_configs WHERE experiment_id = $exp AND name = 'montagem sem escala' ORDER BY id DESC LIMIT 1").Trim()
Mostrar @('uv run barnes metrics process --video $v1 --maze-config-id $maze0 --trial $t1 --trajectory data\interim\traj_demo.csv')
uv run barnes metrics process --video $v1 --maze-config-id $maze0 --trial $t1 --trajectory data\interim\traj_demo.csv
Mostrar @('uv run barnes video load $vs --experiment-id $exp --maze-config-id $maze0 --day 3 --no-preview')
uv run barnes video load $vs --experiment-id $exp --maze-config-id $maze0 --day 3 --no-preview
Mostrar @('$t0 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $maze0 ORDER BY id DESC LIMIT 1").Trim()')
$t0 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $maze0 ORDER BY id DESC LIMIT 1").Trim()
Mostrar @('uv run barnes metrics process --video $vs --trial $t0 --trajectory data\interim\traj_demo.csv')
uv run barnes metrics process --video $vs --trial $t0 --trajectory data\interim\traj_demo.csv
Mostrar @('uv run barnes metrics process --video $vs --trial $t1 --trajectory data\interim\traj_demo.csv')
uv run barnes metrics process --video $vs --trial $t1 --trajectory data\interim\traj_demo.csv
Janela 'B.5/B.8: clique nas pontas de dois diâmetros da plataforma (4 cliques) e Enter. Botão direito desfaz, R recomeça.'
Mostrar @('uv run barnes scale calibrate --video $v1 --maze-config-id $maze --length-1-cm $arena_cm --length-2-cm $arena_cm')
uv run barnes scale calibrate --video $v1 --maze-config-id $maze --length-1-cm $arena_cm --length-2-cm $arena_cm
Mostrar @('uv run barnes metrics executions --trial $t1')
uv run barnes metrics executions --trial $t1
Mostrar @('uv run barnes metrics process --video $v1 --trial $t1 --trajectory data\interim\traj_demo.csv')
uv run barnes metrics process --video $v1 --trial $t1 --trajectory data\interim\traj_demo.csv
Mostrar @('uv run barnes metrics executions --trial $t1')
uv run barnes metrics executions --trial $t1
Mostrar @('uv run pytest tests/metrics/test_metrics.py tests/test_cli.py -v')
uv run pytest tests/metrics/test_metrics.py tests/test_cli.py -v
Pausa

Titulo 'B.9' 'US-06 — Anotação de quadros para o modelo de pose'
Mostrar @('uv run barnes pose sample --video $v1 --maze-config-id $maze --out $anot')
uv run barnes pose sample --video $v1 --maze-config-id $maze --out $anot
Mostrar @('uv run barnes pose sample --video $v2 --maze-config-id $maze --out $anot')
uv run barnes pose sample --video $v2 --maze-config-id $maze --out $anot
Mostrar @('uv run barnes pose sample --video $v1 --maze-config-id $maze --out $anot')
uv run barnes pose sample --video $v1 --maze-config-id $maze --out $anot
Mostrar @('uv run barnes pose sample --video $vc --maze-config-id $mazec --start-frame 2038 --end-frame 6750 --out $anot')
uv run barnes pose sample --video $vc --maze-config-id $mazec --start-frame 2038 --end-frame 6750 --out $anot
Mostrar @('@''', '... (script de 13 linhas, ver o roteiro)')
@'
import csv, pathlib
from barnes.pose.annotations import AnnotatedFrame, write_annotations_csv
base = pathlib.Path("data/demo_anotacao")
frames = []
for amostra in base.glob("*/amostragem.csv"):
    with amostra.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            p = (float(row["x_px"]), float(row["y_px"]))
            frames.append(AnnotatedFrame(row["trial"], int(row["quadro"]), (p, p, p)))
write_annotations_csv(frames, base / "anotacoes.csv")
print(f"{len(frames)} quadros com anotacao SIMULADA")
'@ | uv run python -
Mostrar @('uv run barnes pose report --annotations $anot\anotacoes.csv --samples $anot')
uv run barnes pose report --annotations $anot\anotacoes.csv --samples $anot
Mostrar @('uv run barnes pose split --annotations $anot\anotacoes.csv --out $anot\divisao.csv')
uv run barnes pose split --annotations $anot\anotacoes.csv --out $anot\divisao.csv
Mostrar @('uv run barnes pose check-split --manifest $anot\divisao.csv')
uv run barnes pose check-split --manifest $anot\divisao.csv
Mostrar @('Set-Content -Path $anot\divisao_ok.csv -Value "trial,quadro,conjunto","aaa,0,treino","aaa,25,treino","bbb,0,validacao","ccc,0,teste" -Encoding utf8')
Set-Content -Path $anot\divisao_ok.csv -Value "trial,quadro,conjunto","aaa,0,treino","aaa,25,treino","bbb,0,validacao","ccc,0,teste" -Encoding utf8
Mostrar @('uv run barnes pose check-split --manifest $anot\divisao_ok.csv')
uv run barnes pose check-split --manifest $anot\divisao_ok.csv
Mostrar @('Set-Content -Path $anot\divisao_vazada.csv -Value "trial,quadro,conjunto","aaa,0,treino","aaa,25,teste","bbb,0,validacao" -Encoding utf8')
Set-Content -Path $anot\divisao_vazada.csv -Value "trial,quadro,conjunto","aaa,0,treino","aaa,25,teste","bbb,0,validacao" -Encoding utf8
Mostrar @('uv run barnes pose check-split --manifest $anot\divisao_vazada.csv')
uv run barnes pose check-split --manifest $anot\divisao_vazada.csv
Mostrar @('uv run pytest tests/pose -v')
uv run pytest tests/pose -v
Pausa

Titulo 'B.10' 'US-07 — Ambiente e treino do modelo de pose'
Mostrar @('uv run barnes pose hardware --out $posedemo\hardware.json')
uv run barnes pose hardware --out $posedemo\hardware.json
Mostrar @('uv run barnes pose plan-training --report $posedemo\hardware.json --out $posedemo\plano-1.json')
uv run barnes pose plan-training --report $posedemo\hardware.json --out $posedemo\plano-1.json
Mostrar @('uv run barnes pose plan-training --report $posedemo\hardware.json --institutional sim --out $posedemo\plano-2.json')
uv run barnes pose plan-training --report $posedemo\hardware.json --institutional sim --out $posedemo\plano-2.json
Mostrar @('uv run barnes pose plan-training --report $posedemo\hardware.json --institutional nao --kaggle sim --out $posedemo\plano-3.json')
uv run barnes pose plan-training --report $posedemo\hardware.json --institutional nao --kaggle sim --out $posedemo\plano-3.json
Mostrar @('uv run barnes pose plan-training --report $posedemo\hardware.json --institutional nao --kaggle sim --d4-reference "SIMULADO - so para a demonstracao" --out $posedemo\plano-4.json')
uv run barnes pose plan-training --report $posedemo\hardware.json --institutional nao --kaggle sim --d4-reference "SIMULADO - so para a demonstracao" --out $posedemo\plano-4.json
Mostrar @('Get-Content $posedemo\plano-4.json')
Get-Content $posedemo\plano-4.json
Mostrar @('uv run barnes pose train --dataset $posedemo\sem-pacote')
uv run barnes pose train --dataset $posedemo\sem-pacote
Mostrar @('uv run pytest tests/pose/test_environment.py tests/pose/test_dataset.py tests/pose/test_training.py tests/pose/test_cli_training.py -v')
uv run pytest tests/pose/test_environment.py tests/pose/test_dataset.py tests/pose/test_training.py tests/pose/test_cli_training.py -v
Pausa

Titulo 'B.11' 'US-08 — Avaliação por região e inferência local'
Mostrar @('New-Item -ItemType Directory -Force $posedemo\modelo-interrompido | Out-Null')
New-Item -ItemType Directory -Force $posedemo\modelo-interrompido | Out-Null
Mostrar @('Set-Content -Path $posedemo\modelo-interrompido\manifest.json -Value ''{"schema_version": 1, "status": "running"}'' -Encoding ascii')
Set-Content -Path $posedemo\modelo-interrompido\manifest.json -Value '{"schema_version": 1, "status": "running"}' -Encoding ascii
Mostrar @('uv run barnes pose infer --model $posedemo\modelo-interrompido --trial $t1')
uv run barnes pose infer --model $posedemo\modelo-interrompido --trial $t1
Mostrar @('uv run pytest tests/pose/test_evaluation.py -v')
uv run pytest tests/pose/test_evaluation.py -v
Mostrar @('uv run pytest tests/pose/test_inference.py tests/pose/test_offline.py -v')
uv run pytest tests/pose/test_inference.py tests/pose/test_offline.py -v
Pausa

Titulo 'B.12' 'US-09 — Série de posição e orientação da cabeça'
Mostrar @('$inf = "$posedemo\inferencia-simulada-t$tc"')
$inf = "$posedemo\inferencia-simulada-t$tc"
Mostrar @('@''', '... (script de 92 linhas, ver o roteiro)')
@'
import json, math, pathlib, sys, time
import numpy as np
from barnes.db.connection import get_connection
from barnes.db.maze_configs import get_maze_config
from barnes.db.pose_executions import get_inference_trial
from barnes.io.video import iter_frames
from barnes.pose.annotations import KEYPOINTS, trial_key
from barnes.pose.dataset import file_sha256
from barnes.pose.sampling import build_background, estimate_animal_position
from barnes.pose.series import POSE_CSV_COLUMNS
started = time.perf_counter()
trial, out = int(sys.argv[1]), pathlib.Path(sys.argv[2])
with get_connection() as conn:
    t = get_inference_trial(conn, trial)
    geometry = get_maze_config(conn, t.maze_config_id)
iv, fps, n = t.interval, t.fps_real, t.frame_count
# Os mesmos quadros que o `pose infer` processaria (barnes.pose.inference.infer_trial).
first = max(iv.start_frame, math.ceil(iv.start_s * fps))
last = min(iv.end_frame, math.floor(iv.end_s * fps), n - 1)
if first > 0 and (first - 1) / fps >= iv.start_s:
    first -= 1
if last + 1 < n and (last + 1) / fps <= iv.end_s:
    last += 1
frames = np.arange(first, last + 1)
m = len(frames)
if m < 120:
    sys.exit("Intervalo util curto demais para a simulacao (menos de 120 quadros).")
# Centro do corpo pela segmentacao por contraste do US-06.
background = build_background(t.filepath, first, last)
center = {}
for index, image in iter_frames(t.filepath, first, last, lambda i: True):
    center[index] = estimate_animal_position(image, background, geometry)
found = np.array([center.get(int(f)) is not None for f in frames])
if not found.any():
    sys.exit("O contraste nao encontrou o animal em nenhum quadro do intervalo.")
# Quadros em que o contraste falhou sao preenchidos aqui: as unicas falhas da pose
# simulada sao as tres lacunas injetadas abaixo.
cx = np.interp(frames, frames[found], [center[int(f)][0] for f in frames[found]])
cy = np.interp(frames, frames[found], [center[int(f)][1] for f in frames[found]])
# Eixo do corpo = direcao do movimento em 0,2 s; parado, mantem a direcao anterior.
k = max(1, round(fps / 5))
ahead, behind = np.minimum(np.arange(m) + k, m - 1), np.maximum(np.arange(m) - k, 0)
dx, dy = cx[ahead] - cx[behind], cy[ahead] - cy[behind]
angle = np.arctan2(dy, dx)
for i in range(1, m):
    if math.hypot(dx[i], dy[i]) < 1.0:
        angle[i] = angle[i - 1]
half = 0.1 * geometry.platform_radius_px
ux, uy = np.cos(angle), np.sin(angle)
points = {
    "focinho": [cx + half * ux, cy + half * uy],
    "centro_corpo": [cx.copy(), cy.copy()],
    "base_cauda": [cx - half * ux, cy - half * uy],
}
def gap(fraction, length):
    start = int(fraction * m)
    return start, start + length - 1
gaps = [
    ("focinho", gap(0.20, 3), "curta: sera interpolada"),
    ("focinho", gap(0.45, 15), "longa: corrigir na revisao (B.13)"),
    ("base_cauda", gap(0.75, max(15, round(0.07 * m))), "longa: revisar sem corrigir (B.13)"),
]
for point, (a, b), _ in gaps:
    points[point][0][a:b + 1] = np.nan
    points[point][1][a:b + 1] = np.nan
out.mkdir(parents=True, exist_ok=True)
pose_csv = out / "pose.csv"
with pose_csv.open("w", encoding="utf-8", newline="") as f:
    f.write(",".join(POSE_CSV_COLUMNS) + "\n")
    for i, frame in enumerate(frames):
        row = [trial_key(t.content_hash), str(int(frame)), str(float(frame) / fps)]
        for p in KEYPOINTS:
            x, y = float(points[p][0][i]), float(points[p][1][i])
            row += ["", "", ""] if math.isnan(x) else [str(x), str(y), "0.9"]
        f.write(",".join(row) + "\n")
record = {
    "schema_version": 1, "status": "completed", "kind": "inferencia",
    "model_id": "simulado-demo", "dataset_id": "simulado-demo",
    "maze_config_id": t.maze_config_id, "trial_id": trial,
    "content_hash": t.content_hash, "video": str(t.filepath), "fps": fps,
    "processed_interval_frames": {"start": int(first), "end": int(last)},
    "duration_seconds": time.perf_counter() - started,
    "artifacts": {"pose.csv": file_sha256(pose_csv)},
    "simulado": "POSE SIMULADA para a demonstracao: nao e saida de um modelo treinado.",
}
(out / "execucao.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print("Inferencia SIMULADA em %s | quadros %d a %d" % (out, first, last))
for point, (a, b), what in gaps:
    print("  lacuna injetada: %s, quadros %d-%d (%d quadros), %s"
          % (point, frames[a], frames[b], b - a + 1, what))
'@ | uv run python - $tc $inf
Mostrar @('uv run barnes pose series --trial $tc --inference $inf --out $interim')
uv run barnes pose series --trial $tc --inference $inf --out $interim
Mostrar @('$mostrar_serie = @''', '... (script de 35 linhas, ver o roteiro)')
$mostrar_serie = @'
import sys
from barnes.pose.trajectory import read_metadata, read_trajectory
table = read_trajectory(sys.argv[1])  # le e confere o contrato da trajetoria
d, meta = table.to_pydict(), read_metadata(table)
q = d["quadro"]
print("contrato v%s | trial %s | execucao %s | modelo %s" % (
    meta["contrato_versao"], meta["trial_id"], meta["execucao_id"], meta["model_id"]))
print("%d linhas = quadros %d a %d | t_s de %.2f a %.2f s | escala %.4f cm/px | fps variavel: %s"
      % (len(q), q[0], q[-1], d["t_s"][0], d["t_s"][-1], meta["cm_per_px"], meta["fps_variavel"]))
def show(title, row):
    print("\n" + title)
    print(" quadro    t_s  focinho_x  focinho_y   theta  pose_valida  cauda_valida  interpolado")
    for i in range(max(row - 2, 0), min(row + 5, len(q))):
        print("%7d %6.2f %10.1f %10.1f %7.1f %12s %13s %12s" % (
            q[i], d["t_s"][i], d["focinho_x_cm_image"][i], d["focinho_y_cm_image"][i],
            d["theta_deg_image"][i], d["pose_valida"][i], d["base_cauda_valido"][i],
            d["interpolado"][i]))
for title, column, value in (
    ("Lacuna curta: preenchida e marcada (US-10 Cenario 1)", "interpolado", True),
    ("Sem focinho: ausente, sem repetir o quadro anterior (US-09 Cenario 3)", "pose_valida", False),
    ("Sem base da cauda", "base_cauda_valido", False),
):
    row = next((i for i, v in enumerate(d[column]) if v == value), None)
    if row is not None:
        show(title, row)
rep = meta.get("pos_processamento")
if rep:
    print("\ncobertura %.3f (so deteccao %.3f, minimo %.2f) | qualidade: %s" % (
        rep["cobertura"], rep["cobertura_deteccao"], rep["cobertura_minima"], rep["qualidade"]))
    for s in rep["trechos_sinalizados"]:
        print("trecho sinalizado: quadros %d-%d, faltam %s, %s" % (
            s["inicio"], s["fim"], ", ".join(s["pontos"]),
            "PENDENTE" if s["pendente"] else "revisado"))
'@
Mostrar @('$serie = "$interim\trial_$tc.parquet"')
$serie = "$interim\trial_$tc.parquet"
Mostrar @('$mostrar_serie | uv run python - $serie')
$mostrar_serie | uv run python - $serie
Mostrar @('$exec_serie = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT cobertura_execucao_id FROM trials WHERE id = $tc").Trim()')
$exec_serie = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT cobertura_execucao_id FROM trials WHERE id = $tc").Trim()
Mostrar @('uv run barnes execution show $exec_serie')
uv run barnes execution show $exec_serie
Mostrar @('uv run barnes pose series --trial $t1 --inference $inf --out $interim')
uv run barnes pose series --trial $t1 --inference $inf --out $interim
Mostrar @('uv run pytest tests/pose/test_series.py tests/pose/test_trajectory.py tests/pose/test_series_from_inference.py -v')
uv run pytest tests/pose/test_series.py tests/pose/test_trajectory.py tests/pose/test_series_from_inference.py -v
Pausa

Titulo 'B.13' 'US-10 — Suavização, interpolação e revisão de falhas de pose'
Mostrar @('Select-String -Path configs\default.yaml -Pattern "cobertura_minima|lacuna_curta_max_quadros|metodo|janela_quadros"')
Select-String -Path configs\default.yaml -Pattern "cobertura_minima|lacuna_curta_max_quadros|metodo|janela_quadros"
Janela 'B.13: abre no trecho do focinho: d 5x e clique no focinho, d 5x e clique de novo, Enter; no trecho da cauda, Enter sem marcar; s salva.'
Mostrar @('uv run barnes pose review --trial $tc')
uv run barnes pose review --trial $tc
Mostrar @('$mostrar_serie | uv run python - $serie')
$mostrar_serie | uv run python - $serie
Mostrar @('$rev = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT cobertura_execucao_id FROM trials WHERE id = $tc").Trim()')
$rev = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT cobertura_execucao_id FROM trials WHERE id = $tc").Trim()
Mostrar @('uv run barnes execution show $rev')
uv run barnes execution show $rev
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT id, execucao_id, quadro, ponto, round(x_px::numeric,1) AS x_px, round(y_px::numeric,1) AS y_px FROM correcao_pose WHERE trial_id = $tc ORDER BY id"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT id, execucao_id, quadro, ponto, round(x_px::numeric,1) AS x_px, round(y_px::numeric,1) AS y_px FROM correcao_pose WHERE trial_id = $tc ORDER BY id"
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "UPDATE correcao_pose SET x_px = 0 WHERE trial_id = $tc"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "UPDATE correcao_pose SET x_px = 0 WHERE trial_id = $tc"
Mostrar @('uv run barnes catalog list')
uv run barnes catalog list
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT * FROM qualidade_pose WHERE trial_id = $tc"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT * FROM qualidade_pose WHERE trial_id = $tc"
Mostrar @('uv run barnes pose series --trial $tc --inference $inf --out $interim')
uv run barnes pose series --trial $tc --inference $inf --out $interim
Mostrar @('uv run barnes pose review --trial $tc')
uv run barnes pose review --trial $tc
Mostrar @('uv run pytest tests/pose/test_quality.py tests/pose/test_review_ui.py tests/db/test_pose_corrections.py -v')
uv run pytest tests/pose/test_quality.py tests/pose/test_review_ui.py tests/db/test_pose_corrections.py -v
Pausa

Titulo 'B.14' 'US-27 — Proveniência das execuções e catálogo de trials'
Mostrar @('uv run barnes metrics executions --trial $t1 --history')
uv run barnes metrics executions --trial $t1 --history
Mostrar @('$exec = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT execucao_id FROM trial_results WHERE trial_id = $t1 ORDER BY id DESC LIMIT 1").Trim()')
$exec = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT execucao_id FROM trial_results WHERE trial_id = $t1 ORDER BY id DESC LIMIT 1").Trim()
Mostrar @('uv run barnes execution show $exec')
uv run barnes execution show $exec
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT id, trial_id, kind, coalesce(model_id, ''-'') AS modelo, parametros->>''comando'' AS comando, git_dirty AS sujo, recorded_at::timestamp(0) AS registrada FROM execucao WHERE trial_id IN ($t1, $tc) ORDER BY id"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT id, trial_id, kind, coalesce(model_id, '-') AS modelo, parametros->>'comando' AS comando, git_dirty AS sujo, recorded_at::timestamp(0) AS registrada FROM execucao WHERE trial_id IN ($t1, $tc) ORDER BY id"
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "INSERT INTO trial_results (trial_id, distance_cm) VALUES ($t1, 1.0)"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "INSERT INTO trial_results (trial_id, distance_cm) VALUES ($t1, 1.0)"
Mostrar @('uv run barnes catalog list')
uv run barnes catalog list
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT * FROM sessao WHERE experiment_id = $exp"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT * FROM sessao WHERE experiment_id = $exp"
Mostrar @('New-Item -ItemType Directory -Force data\raw\movidos | Out-Null')
New-Item -ItemType Directory -Force data\raw\movidos | Out-Null
Mostrar @('Move-Item $v1 data\raw\movidos\renomeado.mp4')
Move-Item $v1 data\raw\movidos\renomeado.mp4
Mostrar @('uv run barnes catalog list --procurar-em data\raw\movidos')
uv run barnes catalog list --procurar-em data\raw\movidos
Mostrar @('uv run barnes metrics process --video data\raw\movidos\renomeado.mp4 --trial $t1 --trajectory data\interim\traj_demo.csv')
uv run barnes metrics process --video data\raw\movidos\renomeado.mp4 --trial $t1 --trajectory data\interim\traj_demo.csv
Mostrar @('Move-Item data\raw\movidos\renomeado.mp4 $v1')
Move-Item data\raw\movidos\renomeado.mp4 $v1
Mostrar @('Copy-Item $vs "$vs.bak"')
Copy-Item $vs "$vs.bak"
Mostrar @('Copy-Item data\raw\corrompido.mp4 $vs -Force')
Copy-Item data\raw\corrompido.mp4 $vs -Force
Mostrar @('uv run barnes catalog list')
uv run barnes catalog list
Mostrar @('Move-Item "$vs.bak" $vs -Force')
Move-Item "$vs.bak" $vs -Force
Mostrar @('uv run barnes catalog list --verificar-hash')
uv run barnes catalog list --verificar-hash
Mostrar @('Set-Content -Path demo_alteracao_nao_commitada.txt -Value "simula uma alteracao nao commitada" -Encoding utf8')
Set-Content -Path demo_alteracao_nao_commitada.txt -Value "simula uma alteracao nao commitada" -Encoding utf8
Mostrar @('uv run barnes metrics process --video $v1 --trial $t1 --trajectory data\interim\traj_demo.csv')
uv run barnes metrics process --video $v1 --trial $t1 --trajectory data\interim\traj_demo.csv
Mostrar @('$sujo = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT max(id) FROM execucao WHERE trial_id = $t1").Trim()')
$sujo = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT max(id) FROM execucao WHERE trial_id = $t1").Trim()
Mostrar @('uv run barnes execution show $sujo')
uv run barnes execution show $sujo
Mostrar @('Remove-Item demo_alteracao_nao_commitada.txt')
Remove-Item demo_alteracao_nao_commitada.txt
Mostrar @('uv run pytest tests/db/test_us27_schema.py tests/db/test_catalog.py tests/test_provenance.py tests/io/test_verify_video.py -v')
uv run pytest tests/db/test_us27_schema.py tests/db/test_catalog.py tests/test_provenance.py tests/io/test_verify_video.py -v
Pausa

Titulo 'B.15' 'US-11 — Detecção do evento de descoberta (D)'
Mostrar @('Select-String -Path configs\default.yaml -Pattern "encontrar:|distancia_cm|angulo_graus|calibrado_contra_anotacao"')
Select-String -Path configs\default.yaml -Pattern "encontrar:|distancia_cm|angulo_graus|calibrado_contra_anotacao"
Mostrar @('uv run barnes events discover --trial $tc')
uv run barnes events discover --trial $tc
Mostrar @('Move-Item $vc data\raw\movidos\completo.mp4')
Move-Item $vc data\raw\movidos\completo.mp4
Mostrar @('uv run barnes events discover --trial $tc')
uv run barnes events discover --trial $tc
Mostrar @('Move-Item data\raw\movidos\completo.mp4 $vc')
Move-Item data\raw\movidos\completo.mp4 $vc
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT h.hole_number, e.tipo, e.quadro, round(e.t_s::numeric,2) AS t_s, round(e.distancia_cm::numeric,2) AS distancia_cm, round(e.angulo_deg::numeric,1) AS angulo_deg FROM evento_buraco e JOIN holes h ON h.id = e.hole_id WHERE e.trial_id = $tc ORDER BY e.t_s"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT h.hole_number, e.tipo, e.quadro, round(e.t_s::numeric,2) AS t_s, round(e.distancia_cm::numeric,2) AS distancia_cm, round(e.angulo_deg::numeric,1) AS angulo_deg FROM evento_buraco e JOIN holes h ON h.id = e.hole_id WHERE e.trial_id = $tc ORDER BY e.t_s"
Mostrar @('$exec_evt = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT max(id) FROM execucao WHERE trial_id = $tc AND parametros->>''comando'' = ''events discover''").Trim()')
$exec_evt = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT max(id) FROM execucao WHERE trial_id = $tc AND parametros->>'comando' = 'events discover'").Trim()
Mostrar @('uv run barnes execution show $exec_evt')
uv run barnes execution show $exec_evt
Mostrar @('Set-Content -Path $interim\limiares_teste.yaml -Value "encontrar:","  distancia_cm: 20","  angulo_graus: 90" -Encoding utf8')
Set-Content -Path $interim\limiares_teste.yaml -Value "encontrar:","  distancia_cm: 20","  angulo_graus: 90" -Encoding utf8
Mostrar @('uv run barnes events discover --trial $tc --config $interim\limiares_teste.yaml')
uv run barnes events discover --trial $tc --config $interim\limiares_teste.yaml
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT execucao_id, hole_id, quadro, t_s FROM evento_buraco WHERE trial_id = $tc ORDER BY execucao_id, hole_id"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT execucao_id, hole_id, quadro, t_s FROM evento_buraco WHERE trial_id = $tc ORDER BY execucao_id, hole_id"
Mostrar @('uv run pytest tests/events/test_discovery.py tests/db/test_maze_configs.py -v')
uv run pytest tests/events/test_discovery.py tests/db/test_maze_configs.py -v
Pausa

Titulo 'B.16' 'US-13/US-14/US-15 — Entrada, dwell e sequência de visitação (e US-12 bloqueada)'
Mostrar @('Select-String -Path configs\default.yaml -Pattern "versao_definicoes|raio_fator|duracao_minima_s: 0|tempo_limite_s|criterio:"')
Select-String -Path configs\default.yaml -Pattern "versao_definicoes|raio_fator|duracao_minima_s: 0|tempo_limite_s|criterio:"
Mostrar @('uv run barnes db migrate')
uv run barnes db migrate
Mostrar @('uv run barnes events enter --trial $tc --out data\demo_events')
uv run barnes events enter --trial $tc --out data\demo_events
Mostrar @('$entrada = (Get-ChildItem data\demo_events -Directory -Filter entry-* | Sort-Object LastWriteTime | Select-Object -Last 1).FullName')
$entrada = (Get-ChildItem data\demo_events -Directory -Filter entry-* | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
Mostrar @('Import-Csv "$entrada\entries.csv" | Format-Table hole_number_platform, t_s, discovery_t_s, delta_latency, delta_distance, dwell_s, dwell_interpolado, qualidade_pose')
Import-Csv "$entrada\entries.csv" | Format-Table hole_number_platform, t_s, discovery_t_s, delta_latency, delta_distance, dwell_s, dwell_interpolado, qualidade_pose
Mostrar @('uv run barnes events sequence --trial $tc --out data\demo_events')
uv run barnes events sequence --trial $tc --out data\demo_events
Mostrar @('$sequencia = (Get-ChildItem data\demo_events -Directory -Filter sequence-* | Sort-Object LastWriteTime | Select-Object -Last 1).FullName')
$sequencia = (Get-ChildItem data\demo_events -Directory -Filter sequence-* | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
Mostrar @('Import-Csv "$sequencia\sequencia.csv" | Format-Table ordem, buraco_platform, angulo_deg_room, t_descoberta_s, t_entrada_s, dwell_s, alvo')
Import-Csv "$sequencia\sequencia.csv" | Format-Table ordem, buraco_platform, angulo_deg_room, t_descoberta_s, t_entrada_s, dwell_s, alvo
Mostrar @('$exec_ent = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT max(id) FROM execucao WHERE trial_id = $tc AND parametros->>''comando'' = ''events enter''").Trim()')
$exec_ent = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT max(id) FROM execucao WHERE trial_id = $tc AND parametros->>'comando' = 'events enter'").Trim()
Mostrar @('uv run barnes execution show $exec_ent')
uv run barnes execution show $exec_ent
Mostrar @('uv run barnes events calibrate --trial $tc --out data\demo_events\calibracao')
uv run barnes events calibrate --trial $tc --out data\demo_events\calibracao
Mostrar @('uv run pytest tests/metrics/test_latency.py tests/metrics/test_errors.py tests/events/test_sequence.py -v')
uv run pytest tests/metrics/test_latency.py tests/metrics/test_errors.py tests/events/test_sequence.py -v
Pausa

Titulo 'B.17' 'US-18 — Distância total e velocidade média'
Mostrar @('uv run barnes db migrate')
uv run barnes db migrate
Mostrar @('uv run barnes metrics displacement --trial $tc')
uv run barnes metrics displacement --trial $tc
Mostrar @('Move-Item $vc data\raw\movidos\completo.mp4')
Move-Item $vc data\raw\movidos\completo.mp4
Mostrar @('uv run barnes metrics displacement --trial $tc')
uv run barnes metrics displacement --trial $tc
Mostrar @('Move-Item data\raw\movidos\completo.mp4 $vc')
Move-Item data\raw\movidos\completo.mp4 $vc
Mostrar @('docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT tr.execucao_id, round(tr.distance_cm::numeric,2) AS distancia_cm, round(tr.speed_mean_cm::numeric,2) AS velocidade_cm_s, round(tr.interpolated_fraction::numeric,3) AS fracao_interpolada, t.fps_is_variable AS ressalva_velocidade FROM trial_results tr JOIN trials t ON t.id = tr.trial_id WHERE tr.trial_id = $tc ORDER BY tr.execucao_id"')
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT tr.execucao_id, round(tr.distance_cm::numeric,2) AS distancia_cm, round(tr.speed_mean_cm::numeric,2) AS velocidade_cm_s, round(tr.interpolated_fraction::numeric,3) AS fracao_interpolada, t.fps_is_variable AS ressalva_velocidade FROM trial_results tr JOIN trials t ON t.id = tr.trial_id WHERE tr.trial_id = $tc ORDER BY tr.execucao_id"
Mostrar @('uv run barnes metrics distance-validate --saida data\demo_validation')
uv run barnes metrics distance-validate --saida data\demo_validation
Mostrar @('uv run pytest tests/metrics/test_displacement.py tests/metrics/test_validation.py tests/metrics/test_cli_metrics.py tests/metrics/test_cli_metrics_postgres.py -v')
uv run pytest tests/metrics/test_displacement.py tests/metrics/test_validation.py tests/metrics/test_cli_metrics.py tests/metrics/test_cli_metrics_postgres.py -v
Pausa

Titulo 'B.18' 'US-28 — Trial de referência e teste de regressão'
Mostrar @('uv run pytest tests/test_us28_trial_referencia.py -v')
uv run pytest tests/test_us28_trial_referencia.py -v
Mostrar @('Copy-Item tests\fixtures\trial_referencia_esperado.yaml $env:TEMP\esperado_us28.bak', '@''', 'from pathlib import Path', 'p = Path("tests/fixtures/trial_referencia_esperado.yaml")', 'p.write_text(p.read_text(encoding="utf-8").replace("total_errors: 1", "total_errors: 2"), encoding="utf-8")', '''@ | uv run python -', 'uv run pytest tests/test_us28_trial_referencia.py -q --tb=short')
Copy-Item tests\fixtures\trial_referencia_esperado.yaml $env:TEMP\esperado_us28.bak
@'
from pathlib import Path
p = Path("tests/fixtures/trial_referencia_esperado.yaml")
p.write_text(p.read_text(encoding="utf-8").replace("total_errors: 1", "total_errors: 2"), encoding="utf-8")
'@ | uv run python -
uv run pytest tests/test_us28_trial_referencia.py -q --tb=short
Mostrar @('Copy-Item $env:TEMP\esperado_us28.bak tests\fixtures\trial_referencia_esperado.yaml -Force', 'uv run pytest tests/test_us28_trial_referencia.py -q')
Copy-Item $env:TEMP\esperado_us28.bak tests\fixtures\trial_referencia_esperado.yaml -Force
uv run pytest tests/test_us28_trial_referencia.py -q
Pausa

Titulo 'C' 'Encerramento'
Mostrar @('Remove-Item Env:BARNES_DATABASE_URL, Env:BARNES_TEST_DATABASE_URL')
Remove-Item Env:BARNES_DATABASE_URL, Env:BARNES_TEST_DATABASE_URL
Mostrar @('Test-Path $v1, $vc')
Test-Path $v1, $vc
Mostrar @('git status --short')
git status --short
# Opcional, apaga o banco de demonstração:
# docker exec barnes-maze-postgres-1 psql -U barnes -d barnes -c "DROP DATABASE IF EXISTS barnes_demo"
Pausa

Write-Host ''
Write-Host 'Roteiro concluído.' -ForegroundColor Green

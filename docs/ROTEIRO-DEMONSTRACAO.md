# Roteiro de demonstração ao cliente (LNBio): Sprint 1

Comandos, na ordem, para demonstrar **todos os cards do Sprint 1 (US-01 a US-06)**.
Cada passo indica o cenário de aceite do card (`docs/CARDS.md`, com os ajustes de
`docs/revisao-cards.md`) que ele demonstra.

| Card | Tema | Seção |
|---|---|---|
| US-01 | Leitura do vídeo e metadados | B.4 |
| US-02 | Escala px→cm e métricas em cm | B.5 e B.8 |
| US-03 | Recorte do intervalo útil | B.6 e B.8 |
| US-04 | Montagem do labirinto | B.3 |
| US-05 | Rotação e referencial da sala | B.7 |
| US-06 | Anotação para o modelo de pose | B.9 |

A ordem das seções segue a dependência entre os cards, não o número deles: a
montagem (US-04) vem antes da escala e dos trials, porque os dois dependem dela.

**Antes de começar, saiba que:**

- Todos os comandos são para o **PowerShell**, rodados na pasta `barnes-maze` e
  **no mesmo terminal do início ao fim**. As variáveis (`$v1`, `$exp`, `$maze`, ...)
  só existem nesse terminal.
- A demonstração usa um banco **separado**, o `barnes_demo`. O banco de
  desenvolvimento (`barnes`) não é tocado, e o roteiro pode ser repetido quantas
  vezes for preciso.
- Os ids (experimento, montagem, trials) são lidos do banco automaticamente.
  Não há nada para copiar e colar entre os passos.
- Os comandos marcados com 🖱️ abrem uma janela e precisam de interação com o
  mouse ou o teclado.

---

## Parte A — Preparação (fazer ANTES da reunião)

### A.1 Ambiente

Entre na pasta do projeto, que deve estar na branch que será demonstrada (o
`develop` atualizado, com o US-06 e as correções da revisão da Sprint 1).

```powershell
cd barnes-maze
```

Suba o Postgres e instale as dependências. O extra `anotacao` (leitor do
projeto do SLEAP, US-06) é necessário para que nenhum teste fique pulado na B.1:

```powershell
docker compose up -d
```
```powershell
uv sync --system-certs --extra anotacao
```

### A.2 Banco de demonstração limpo

Apague o banco de uma demonstração anterior, se houver, e crie um novo:

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes -c "DROP DATABASE IF EXISTS barnes_demo"
```
```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes -c "CREATE DATABASE barnes_demo"
```

Aponte o sistema para ele e crie as tabelas:

```powershell
$env:BARNES_DATABASE_URL = "postgresql://barnes:barnes@localhost:5432/barnes_demo"
```
```powershell
uv run barnes db migrate
```

Esperado: a lista das migrações aplicadas, da `0001` até a `0005_geometry_px_double.sql`.

Apague também os quadros exportados numa demonstração anterior do US-06 (eles
ficam em disco, não no banco, e a B.9 recusa reamostrar um trial que já tem
quadros):

```powershell
Remove-Item -Recurse -Force data\demo_anotacao -ErrorAction SilentlyContinue
```

### A.3 Arquivos usados na demonstração

Os vídeos reais ficam em `data\raw\` (essa pasta não vai para o git). Ajuste os
nomes se forem outros:

```powershell
$v1 = "data\raw\barnes-sample-1.mp4"
```
```powershell
$v2 = "data\raw\barnes-sample-2.mp4"
```

Gere o vídeo sintético usado para demonstrar a detecção da soltura (US-03).
Ele tem 10 quadros parados e depois um objeto em movimento a partir do quadro 10:

```powershell
uv run python -c "import sys; sys.path.insert(0, 'tests/io'); from pathlib import Path; from test_trim import _write_release_video; _write_release_video(Path('data/raw/sintetico_soltura.mp4'))"
```

(O módulo é importado pelo caminho da pasta, e não como `tests.io.test_trim`,
porque o `sleap-io` instala um pacote próprio chamado `tests` que encobre a
pasta de testes do projeto.)
```powershell
$vs = "data\raw\sintetico_soltura.mp4"
```

Crie um arquivo `.mp4` corrompido (é só texto), para demonstrar o tratamento de
erro do US-01:

```powershell
Set-Content -Path data\raw\corrompido.mp4 -Value "isto nao e um video" -Encoding utf8
```

Crie a trajetória de exemplo usada nas métricas do US-02. O `time_s` é contado
desde o início do vídeo, a mesma referência do intervalo útil do US-03:

```powershell
Set-Content -Path data\interim\traj_demo.csv -Value "x_px,y_px,time_s","10,10,0","40,50,2","70,90,4" -Encoding utf8
```

Pasta dos quadros exportados para anotação no US-06:

```powershell
$anot = "data\demo_anotacao"
```

### A.4 Medidas físicas do labirinto

Use as medidas reais do LNBio. Enquanto a pendência **B2** não for respondida,
use os valores típicos de um labirinto de Barnes para camundongos e **diga isso
ao cliente**:

```powershell
$arena_cm = 92
```
```powershell
$buraco_cm = 5
```

### A.5 Ensaio

Rode a Parte B inteira uma vez antes da reunião. Depois, refaça a A.2 para
começar a reunião com o banco limpo.

---

## Parte B — Demonstração

### B.1 Qualidade: testes automáticos e lint

```powershell
uv run pytest -q
```
```powershell
uv run ruff check src/ tests/
```

Esperado: todos os testes passando, nenhum pulado, e `All checks passed!`.

O que dizer: cada regra de negócio dos cards tem teste automático, e o código
segue um padrão verificado por ferramenta. Os casos que não dá para reproduzir
ao vivo (fps variável, erro < 3% com escala conhecida, ida e volta em todos os
buracos) estão nos testes mostrados em cada card abaixo.

### B.2 Cadastro do experimento

Ainda não existe comando para cadastrar usuário e experimento, então eles são
criados direto no banco:

```powershell
$user = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "INSERT INTO users (email, name) VALUES ('demo@lnbio.local', 'Demonstração') RETURNING id").Trim()
```
```powershell
$exp = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "INSERT INTO experiments (user_id, name) VALUES ($user, 'Experimento demonstração') RETURNING id").Trim()
```
```powershell
"usuário $user, experimento $exp"
```

---

### B.3 US-04 — Montagem paramétrica do labirinto

**Cenário 1 — criar e salvar uma montagem.**

🖱️ Na janela:
1. tecla **`a`**: detecta a borda física da plataforma automaticamente (ponto
   de partida; não é o raio dos buracos);
2. tecla **`h`**: detecta a circunferência dos próprios buracos (precisa de
   pelo menos 3 buracos visíveis) — normalmente mais perto do raio certo que
   o `a`, principalmente se a câmera não estiver perfeitamente perpendicular;
3. **arraste** do centro até o **buraco físico de referência**; ele vira o
   buraco 0, marcado como `ref`;
4. **botão direito** no buraco-alvo, que fica vermelho;
5. **`+`/`-`** ajusta o número de buracos (N);
6. **`[`/`]`** ajusta o raio do buraco, de meio em meio pixel, até o círculo
   desenhado cobrir o buraco real (o valor aparece no rodapé);
7. **`Enter`** confirma.

Atenção: **`Esc` e `q` também confirmam e salvam**, não cancelam. Fechar a
janela "para refazer" grava uma montagem a mais. Se isso acontecer, não tem
problema: o comando abaixo sempre pega a montagem mais recente com esse nome.

O que mostrar: os buracos desenhados coincidem com os buracos reais do vídeo,
**inclusive no tamanho**. As zonas de proximidade dos eventos e a região
"buraco" da anotação (US-06) são medidas em múltiplos desse raio.

```powershell
uv run barnes maze create --experiment-id $exp --name "montagem demo" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm
```
```powershell
$maze = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM maze_configs WHERE experiment_id = $exp AND name = 'montagem demo' ORDER BY id DESC LIMIT 1").Trim()
```
```powershell
"montagem $maze"
```

Esperado: um **único** número.

**Cenário 2 — reaproveitar a montagem sem nenhuma interação.** A geometria é
lida do banco, sem abrir janela:

```powershell
uv run barnes maze show $maze
```

O que mostrar: centro, raio, N, raio do buraco, alvo e cada buraco com o ângulo
`[imagem]` e o ângulo `[sala]`. O buraco 0 aparece como `(REF)` e o alvo como
`(ALVO)`. Na B.6, a mesma montagem é associada a trials novos pelo
`--maze-config-id`; na B.8, as métricas a usam a partir do próprio trial.

**Cenário 3 — parâmetros inválidos.** Cada comando deve recusar a gravação e
dizer qual parâmetro está errado:

N ≤ 2 buracos:
```powershell
uv run barnes maze create --experiment-id $exp --name "invalida" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px 200 --hole-count 2
```

Raio não positivo:
```powershell
uv run barnes maze create --experiment-id $exp --name "invalida" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px -5
```

Alvo fora de 0..N−1:
```powershell
uv run barnes maze create --experiment-id $exp --name "invalida" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px 200 --target-hole-number 25
```

Testes automáticos de geração de buracos e de validação:

```powershell
uv run pytest tests/geometry/test_holes.py tests/geometry/test_validation.py -v
```

---

### B.4 US-01 — Carga do vídeo e leitura dos metadados

**Cenário 1 — vídeo válido.**

🖱️ O comando abre uma janela com o primeiro quadro: `n` avança, `p` volta e `q` fecha.

```powershell
uv run barnes video load $v1
```

O que mostrar: resolução, número de quadros, duração, fps declarado e fps
**real medido** pelos carimbos de tempo, e o hash (sha256) que identifica o
conteúdo do arquivo.

**Cenário 2 — fps variável.** Não há vídeo assim no acervo. Por decisão do grupo
(`revisao-cards.md`), o sistema só avisa. A cobertura está nos testes,
incluindo a regressão com o padrão real de quadros do LNBio:

```powershell
uv run pytest tests/io/test_video.py -v
```

**Cenário 3 — arquivo ilegível.** Cada comando deve parar com uma mensagem que
identifica o arquivo e a causa.

Arquivo que não existe:
```powershell
uv run barnes video load data\raw\nao_existe.mp4 --experiment-id $exp --maze-config-id $maze --no-preview
```

Formato não suportado (só `.mp4` nesta versão):
```powershell
uv run barnes video load data\raw\video.avi --experiment-id $exp --maze-config-id $maze --no-preview
```

Arquivo corrompido:
```powershell
uv run barnes video load data\raw\corrompido.mp4 --experiment-id $exp --maze-config-id $maze --no-preview
```

Nenhum registro parcial foi criado. O esperado é `0`:

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT count(*) AS trials FROM trials"
```

---

### B.5 US-02 — Calibração da escala px→cm

**Cenário 1 — calibração aceita.**

🖱️ Clique nas duas pontas de um diâmetro da plataforma e depois nas duas pontas
de outro diâmetro, mais ou menos perpendicular ao primeiro (4 cliques), e
aperte `Enter`. O botão direito desfaz o último ponto e `R` recomeça.

```powershell
uv run barnes scale calibrate --video $v1 --maze-config-id $maze --length-1-cm $arena_cm --length-2-cm $arena_cm
```

O que mostrar: o fator em cm/px, salvo **na montagem** (vale para todos os
trials gravados com essa câmera).

**Cenário 2 — verificação de exatidão (< 3%).**

🖱️ Marque um **terceiro** diâmetro, na diagonal, diferente dos dois anteriores
(2 cliques), e aperte `Enter`:

```powershell
uv run barnes scale verify --video $v1 --maze-config-id $maze --length-cm $arena_cm
```
```powershell
uv run barnes scale show --maze-config-id $maze
```

O teste automático com uma imagem sintética de escala conhecida:

```powershell
uv run pytest tests/io/test_calibration.py -v
```

O Cenário 3 (bloqueio sem escala) e a regra de recalibração estão na **B.8**,
porque precisam de um trial gravado.

---

### B.6 US-03 — Recorte do intervalo útil do trial

**Detecção automática da soltura** (vídeo sintético). O esperado é
`1.00s (quadro 10) ... — detecção automática`:

```powershell
uv run barnes video load $vs --no-preview
```

**Ajuste manual (Cenário 2), em segundos e em quadros.** O esperado é `ajustado manualmente`:

```powershell
uv run barnes video load $vs --start-s 0.5 --end-s 2.0 --no-preview
```
```powershell
uv run barnes video load $vs --start-frame 3 --end-frame 20 --no-preview
```

**Recusas do recorte.** Cada comando deve terminar com `Erro no intervalo útil: ...`:

```powershell
uv run barnes video load $vs --start-s 1 --start-frame 10 --no-preview
```
```powershell
uv run barnes video load $vs --start-s 2 --end-s 1 --no-preview
```
```powershell
uv run barnes video load $vs --end-s 999 --no-preview
```

**Cenário 1 — gravação dos trials com o intervalo.** Os dois trials abaixo
também são usados no US-05.

Trial 1: dia 1, recorte automático, rotação 0°, que é o padrão porque o LNBio
não rotaciona a plataforma:

```powershell
uv run barnes video load $v1 --experiment-id $exp --maze-config-id $maze --day 1 --trial-in-day 1 --no-preview
```

Trial 2: dia 2, recorte manual a partir de 2 s, rotação de 90°. Os 90°
**simulam** um protocolo que gire a plataforma:

```powershell
uv run barnes video load $v2 --experiment-id $exp --maze-config-id $maze --day 2 --trial-in-day 1 --start-s 2 --rotation-deg 90 --no-preview
```
```powershell
$t1 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE experiment_id = $exp AND day_number = 1 ORDER BY id DESC LIMIT 1").Trim()
```
```powershell
$t2 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE experiment_id = $exp AND day_number = 2 ORDER BY id DESC LIMIT 1").Trim()
```

**O mesmo arquivo não pode entrar duas vezes (US-01, hash).** O trial é
identificado pelo conteúdo, não pelo nome. O esperado é `Erro: Este vídeo já foi
carregado como trial (mesmo conteúdo, hash ...)`, sem traceback:

```powershell
uv run barnes video load $v1 --experiment-id $exp --maze-config-id $maze --day 3 --no-preview
```

**Salvar exige os dois ids.** Com só um deles, o comando recusa em vez de deixar
de salvar sem avisar. O esperado é `Erro: Para salvar o trial, informe
--experiment-id e --maze-config-id juntos ...`:

```powershell
uv run barnes video load $v1 --experiment-id $exp --no-preview
```

**Auditoria: o que ficou gravado em cada trial** (hash do US-01, intervalo do
US-03 e rotação do US-05):

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT id, filename, left(content_hash, 12) AS hash, day_number AS dia, rotation_deg AS rotacao, round(start_time_seconds::numeric,2) AS inicio_s, round(end_time_seconds::numeric,2) AS fim_s, interval_manually_adjusted AS ajuste_manual FROM trials ORDER BY id"
```

**Cenário 3 e RN05 (tempo zero = início do recorte)**, nos testes:

```powershell
uv run pytest tests/io/test_trim.py -v
```

O que dizer, com transparência: nos vídeos reais do LNBio o animal já começa
solto, então a detecção não encontra a soltura e o recorte começa em 0 s. Esse
é o valor correto para esses vídeos, mas a heurística ainda não foi validada
num vídeo real que mostre a soltura.

---

### B.7 US-05 — Rotação da plataforma e referencial da sala

**Cenário 1 — mesma posição na sala, índice diferente.** Os dois trials têm
rotações diferentes (0° e 90°) e foram gravados em dias diferentes. O índice do
buraco-alvo muda, mas o `target_angle_deg_room` é **o mesmo**:

```powershell
uv run barnes trial show $t1
```
```powershell
uv run barnes trial show $t2
```

**Correção da rotação de um trial, inclusive negativa.** O esperado é que fique gravada como 270°:

```powershell
uv run barnes trial set-rotation -- $t2 -90
```
```powershell
uv run barnes trial show $t2
```

**Cenário 3 — trial sem rotação é recusado, nunca vira 0°.** O esperado é uma
recusa que cita o número do trial:

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "UPDATE trials SET rotation_deg = NULL WHERE id = $t2"
```
```powershell
uv run barnes trial show $t2
```

Volte a rotação para 90°:

```powershell
uv run barnes trial set-rotation $t2 90
```

**Cenário 2 — ida e volta índice → sala → índice, para todos os N buracos**,
com vários valores de N, de rotação e de ângulo inicial:

```powershell
uv run pytest tests/geometry/test_reference_frame.py -v
```

O que mostrar no documento: a resposta da B4 e os três referenciais (sufixos
`_image`, `_platform`, `_room`) estão em `docs/definicoes-metricas.md`, seção 6.

---

### B.8 US-02 — Métricas em cm, bloqueio sem escala e recalibração

**Métricas com a escala da montagem**, sem nenhuma nova interação (também é o
Cenário 2 do US-04). A montagem e o intervalo útil vêm do próprio trial; não é
preciso informar `--maze-config-id`:

```powershell
uv run barnes metrics process --video $v1 --trial $t1 --trajectory data\interim\traj_demo.csv
```
```powershell
uv run barnes metrics executions --trial $t1
```

O que mostrar: a distância em cm, a velocidade média em cm/s, o intervalo útil
usado (`interval_start_s`/`interval_end_s`) e o resultado marcado como **atual**.
Como o recorte do trial 1 começa em 0 s (veja a auditoria da B.6), o esperado é
`"samples_outside_interval": 0`. Se a detecção automática tiver marcado outro
início nesse vídeo, as amostras anteriores a ele ficam de fora, e é esse o
comportamento correto.

**US-03 RN02 — nada fora do intervalo útil entra nas métricas.** O trial 2 foi
gravado com o recorte começando em 2 s (B.6). A mesma trajetória tem uma amostra
em 0 s, antes da soltura. O esperado é `"samples_outside_interval": 1`, e a
distância conta só o trecho de 2 s a 4 s (metade da distância do trial 1):

```powershell
uv run barnes metrics process --video $v2 --trial $t2 --trajectory data\interim\traj_demo.csv
```

Se o `$v2` tiver resolução diferente da do `$v1`, o comando recusa (é outra
câmera, que exigiria outra montagem e outra calibração). Nesse caso, mostre o
teste automático `test_nothing_outside_the_useful_interval_enters_the_metrics`
na lista do fim desta seção.

**Escala de outra montagem é recusada.** Crie uma montagem sem calibração:

```powershell
uv run barnes maze create --experiment-id $exp --name "montagem sem escala" --reference-frame $v1 --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm --no-interactive --center-x 300 --center-y 300 --platform-radius-px 200
```
```powershell
$maze0 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM maze_configs WHERE experiment_id = $exp AND name = 'montagem sem escala' ORDER BY id DESC LIMIT 1").Trim()
```

Pedir as métricas do trial 1 com essa montagem é recusado, porque a escala de
outra montagem não vale para ele. O esperado é `Erro: O trial #... é da montagem
#..., não da #...`:

```powershell
uv run barnes metrics process --video $v1 --maze-config-id $maze0 --trial $t1 --trajectory data\interim\traj_demo.csv
```

**Cenário 3 — sem escala calibrada, o cálculo é bloqueado.** Grave um trial na
montagem sem escala (o vídeo sintético, que ainda não foi salvo):

```powershell
uv run barnes video load $vs --experiment-id $exp --maze-config-id $maze0 --day 3 --no-preview
```
```powershell
$t0 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $maze0 ORDER BY id DESC LIMIT 1").Trim()
```

O esperado é `Erro: A montagem ... exige calibração ...`, antes de abrir o vídeo:

```powershell
uv run barnes metrics process --video $vs --trial $t0 --trajectory data\interim\traj_demo.csv
```

**Vídeo de outra resolução é recusado.** O vídeo sintético tem 64×48 px, diferente
do trial 1. O esperado é `Erro: O vídeo informado tem resolução (64, 48), mas o
trial #... foi gravado em ...`:

```powershell
uv run barnes metrics process --video $vs --trial $t1 --trajectory data\interim\traj_demo.csv
```

**RN05 — recalibrar deixa os resultados antigos marcados como obsoletos.**

🖱️ Refaça a calibração (mesmos cliques da B.5):

```powershell
uv run barnes scale calibrate --video $v1 --maze-config-id $maze --length-1-cm $arena_cm --length-2-cm $arena_cm
```

O esperado é o resultado aparecer como **obsoleto**:

```powershell
uv run barnes metrics executions --trial $t1
```

Reprocesse e confira que voltou a ficar atual:

```powershell
uv run barnes metrics process --video $v1 --trial $t1 --trajectory data\interim\traj_demo.csv
```
```powershell
uv run barnes metrics executions --trial $t1
```

Os testes de bloqueio, de escala e de obsolescência:

```powershell
uv run pytest tests/metrics/test_metrics.py tests/test_cli.py -v
```

---

### B.9 US-06 — Anotação de quadros para o modelo de pose

O que dizer antes: o US-06 entrega o **ferramental** de anotação. A rodada de
anotação em si (pessoas marcando os pontos na interface do SLEAP) ainda não
aconteceu: depende dos 3 trials representativos de G1 e da resposta D4. Por
isso, nesta demonstração, a anotação é **simulada** a partir da posição
estimada pelo sistema, e isso precisa ser dito ao cliente.

**Amostragem por região (RN02).** O sistema escolhe os quadros a anotar
cobrindo as três situações do card (centro, borda e proximidade dos buracos),
com a montagem do trial e o intervalo útil do US-03. Cada comando varre o vídeo
inteiro e pode levar alguns minutos:

```powershell
uv run barnes pose sample --video $v1 --maze-config-id $maze --out $anot
```
```powershell
uv run barnes pose sample --video $v2 --maze-config-id $maze --out $anot
```

O que mostrar: em quantos quadros o animal foi encontrado por contraste, e
quantos quadros foram escolhidos por região, com a meta de cada uma. Os PNGs
ficam em `data\demo_anotacao\<trial>\quadros\`, prontos para importar no SLEAP,
e a montagem usada fica registrada em `amostragem.csv`.

Com os vídeos de amostra, de cerca de 15 s, aparece `FALTARAM quadros` em todas
as regiões, **e isso é o esperado**. O protocolo exige 1 s entre quadros
escolhidos (quadros vizinhos são quase idênticos e não ensinam nada ao
modelo), então um vídeo de 15 s rende no máximo cerca de 15 quadros. A meta de
100 por trial é para trials completos, de alguns minutos. O aviso existe
justamente para dizer que aquele trial não basta e que a região precisa de mais
trials.

**Reamostrar não apaga anotação sem querer.** Rodar de novo no mesmo trial é
recusado, porque os quadros podem já estar anotados. O esperado é uma recusa
que sugere `--overwrite`, antes de varrer o vídeo:

```powershell
uv run barnes pose sample --video $v1 --maze-config-id $maze --out $anot
```

**Anotação simulada.** Gera o `anotacoes.csv` no formato interno, como se os
três pontos tivessem sido marcados na posição estimada (na rodada real, este
arquivo vem do `barnes pose import-slp`, que lê os projetos `.slp` do SLEAP):

```powershell
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
```

**Cenário 2 — cobertura por região.** Conta os quadros pelo centro do corpo
anotado, cada trial com a sua própria montagem. O esperado é
`Cobertura OK: as três regiões têm quadros anotados.`, com a proporção de cada
região. Se nesses vídeos o animal nunca passar por alguma região, o comando
**reprova** e diz qual. É o Cenário 2 funcionando: nesse caso, a falta de
quadros também aparece na saída do `pose sample`, como `FALTARAM quadros`.

```powershell
uv run barnes pose report --annotations $anot\anotacoes.csv --samples $anot
```

**Cenário 1 / RN03 — a divisão é por trial, nunca por quadro.** Com só 2 trials
não dá para preencher treino, validação e teste sem repetir trial, e o sistema
**recusa** em vez de dividir por quadro. O esperado é `Erro: São necessários ao
menos 3 trials ...`:

```powershell
uv run barnes pose split --annotations $anot\anotacoes.csv --out $anot\divisao.csv
```

O que dizer: com os 3 trials de G1, fica um trial em cada conjunto. A divisão
com trials suficientes está coberta pelos testes do fim desta seção.

**Cenário 3 — vazamento entre conjuntos.** Um manifesto válido passa:

```powershell
Set-Content -Path $anot\divisao_ok.csv -Value "trial,quadro,conjunto","aaa,0,treino","aaa,25,treino","bbb,0,validacao","ccc,0,teste" -Encoding utf8
```
```powershell
uv run barnes pose check-split --manifest $anot\divisao_ok.csv
```

Um manifesto em que o trial `aaa` aparece em treino **e** em teste falha, e
aponta o trial. O esperado é `Erro: Vazamento entre conjuntos — refaça a
divisão: trial aaa em teste, treino.`:

```powershell
Set-Content -Path $anot\divisao_vazada.csv -Value "trial,quadro,conjunto","aaa,0,treino","aaa,25,teste","bbb,0,validacao" -Encoding utf8
```
```powershell
uv run barnes pose check-split --manifest $anot\divisao_vazada.csv
```

**Testes do US-06**, incluindo a leitura de projetos do SLEAP (`.slp`), a
recusa de projeto com imagens embutidas e a divisão com 3 ou mais trials:

```powershell
uv run pytest tests/pose -v
```

**D4 e protocolo.** Mostre `docs/protocolo-anotacao.md`: os três pontos e sua
ordem (seção 1), as regras de amostragem (seção 2), a divisão por trial
(seção 3) e a tabela da D4 (seção 5), ainda pendente. Nada sai das máquinas do
grupo até a D4 ser respondida.

---

## Parte C — Encerramento

Volte o terminal para o banco de desenvolvimento:

```powershell
Remove-Item Env:BARNES_DATABASE_URL
```

Para apagar o banco de demonstração (opcional; ele é recriado na Parte A da
próxima vez):

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes -c "DROP DATABASE IF EXISTS barnes_demo"
```

---

## O que dizer sobre as pendências (transparência com o cliente)

| Card | Tema | Situação |
|---|---|---|
| US-01 | fps variável | Por decisão do grupo, o sistema só avisa e não corrige. Coberto por teste; não há vídeo assim no acervo. |
| US-02 | Mensagem do bloqueio sem escala | O card pede que a mensagem indique **o comando** para calibrar. Hoje ela diz que a montagem exige calibração, mas não cita o `barnes scale calibrate`. |
| US-02 / US-04 | Medidas físicas (B2) | A demonstração usa 92 cm de plataforma e 5 cm de buraco, que são valores típicos. As distâncias em cm só serão reais com as medidas do LNBio. |
| US-03 | Detecção da soltura | Funciona no vídeo sintético. Nos vídeos reais o animal já começa solto. Pergunta ao LNBio: os vídeos sempre começam assim? |
| US-05 | Buraco físico de referência | Precisa ser combinado com o laboratório (`docs/definicoes-metricas.md`, seção 6.2). |
| US-05 | B4: quem respondeu e quando | A resposta ("não rotaciona") está registrada; faltam o nome de quem respondeu e a data. |
| US-05 | Câmera deslocada entre dias | **Não é detectada automaticamente.** O procedimento é criar uma montagem nova e recalibrar a escala (manual, seção 3.7). Só um vídeo com resolução diferente é recusado automaticamente. |
| US-06 | Rodada de anotação | O ferramental está pronto; a anotação na B.9 é simulada. A rodada real depende dos 3 trials de G1 e da resposta D4 (uso dos quadros e CEUA). |
| US-04 | Raio do buraco | É ajustado a olho na janela (`[`/`]`). Não sai do diâmetro em cm, porque a escala só é calibrada depois da montagem existir. |
| Geral | Trajetória a partir do vídeo | Ainda não existe (Sprint 2). As métricas da demonstração usam uma trajetória de exemplo em CSV. |
| Geral | Cadastro de usuário e experimento | Ainda não há comando nem tela; nesta demonstração ele é feito direto no banco. |

## Se algo der errado

| Sintoma | Solução |
|---|---|
| `... is not recognized as the name of a cmdlet` | O comando foi escrito com a sintaxe do bash. Use `$env:VAR = "..."` em linha separada. |
| Comandos dizem que `BARNES_DATABASE_URL` não está definida | O terminal foi trocado. Repita o `$env:BARNES_DATABASE_URL = ...` da A.2 e as variáveis da A.3 e A.4. |
| `$exp`, `$maze`, `$t1` ou `$t2` vazios | Rode de novo o comando que define a variável e confira com `"$exp $maze $t1 $t2"`. |
| Erro de duplicado na gravação dos trials (B.6) | O banco já tinha esses vídeos. Refaça a A.2 para começar com o banco limpo. |
| `Got unexpected extra argument(s)` num comando com `$maze`, `$t1` etc. | A variável ficou com vários ids (por exemplo, o `maze create` foi rodado mais de uma vez; `Esc`/`q` salvam). Rode de novo o comando que define a variável, que agora pega o mais recente, e confira com `"$maze"`. |
| `No module named 'tests.io.test_trim'` (A.3) | Comando antigo do roteiro. Use o da A.3, que importa `test_trim` pelo caminho `tests/io`. |
| `pose sample` recusa com "--overwrite" no primeiro uso (B.9) | Sobraram quadros de um ensaio anterior. Rode o `Remove-Item` da A.2. |
| `pose report` diz "Montagem desconhecida" | O `--samples` não aponta para a pasta da B.9. Confira `$anot`. |
| `uv sync` com erro de certificado TLS | Use `--system-certs`, como está na A.1. |
| A janela OpenCV não aparece | Ela pode ter aberto atrás do terminal. Procure na barra de tarefas. |

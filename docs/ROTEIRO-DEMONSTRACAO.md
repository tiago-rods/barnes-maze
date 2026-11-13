# Roteiro de demonstração ao cliente (LNBio): Sprints 1 a 3

Comandos, na ordem, para demonstrar **os cards do Sprint 1 (US-01 a US-06)**,
**os do Sprint 2 (US-07, US-08, US-09, US-10, US-27 e US-11)** e **os do Sprint 3
entregues até agora (US-13, US-14, US-15 e US-18; US-12, US-16 e US-17 pelos
testes)**. Cada passo indica o cenário de aceite do card (`docs/CARDS.md`, com os
ajustes de `docs/revisao-cards.md`) que ele demonstra.

Versão explicada, com o fluxo do pipeline e o que faz cada comando:
[`roteiro-demonstracao.html`](roteiro-demonstracao.html) (abrir no navegador). Ela é
gerada a partir deste arquivo; se o roteiro mudar, regenere o HTML.

**Sem contato com o laboratório:** os limiares de entrada, tempo limite e erro usados
a partir da B.16 são decisões da equipe, não do LNBio
(`docs/decisoes-sem-laboratorio.md`). Diga isso ao cliente antes de mostrar números.

| Sprint | Card | Tema | Seção |
|---|---|---|---|
| 1 | US-01 | Leitura do vídeo e metadados | B.4 |
| 1 | US-02 | Escala px→cm e métricas em cm | B.5 e B.8 |
| 1 | US-03 | Recorte do intervalo útil | B.6 e B.8 |
| 1 | US-04 | Montagem do labirinto | B.3 |
| 1 | US-05 | Rotação e referencial da sala | B.7 |
| 1 | US-06 | Anotação para o modelo de pose | B.9 |
| 2 | US-07 | Ambiente e treino do modelo de pose | B.10 |
| 2 | US-08 | Avaliação por região e inferência local | B.11 |
| 2 | US-09 | Série de posição e orientação da cabeça | B.12 |
| 2 | US-10 | Suavização, interpolação e revisão de falhas de pose | B.13 |
| 2 | US-27 | Proveniência das execuções e catálogo de trials | B.8, B.14 |
| 2 | US-11 | Detecção do evento de descoberta (D) | B.15 |
| 3 | US-13 | Entrada física e hesitação D→E | B.16 |
| 3 | US-14 | Dwell (permanência no buraco) | B.16 |
| 3 | US-15 | Sequência de visitação no referencial da sala | B.16 |
| 3 | US-12 | Calibração contra anotação manual — bloqueada sem D3 | B.16 |
| 3 | US-16, US-17 | Latência com censura e contagem de erros — só testes, sem comando | B.16 |
| 3 | US-18 | Distância total e velocidade média | B.17 |
| 3 | US-28 | Trial de referência com teste de regressão | B.18 |

A ordem das seções segue a dependência entre os cards, não o número deles: a
montagem (US-04) vem antes da escala e dos trials, porque os dois dependem dela;
o catálogo (US-27) reúne o que já foi processado quando já há métricas, série de
pose e revisão para mostrar; o evento de descoberta (US-11, B.15) depende da série
de pose da B.12/B.13; e o Sprint 3 (B.16, B.17) vem por último, porque entrada,
sequência e distância dependem da descoberta e da série tratada. A B.18 (US-28)
fecha a parte B: o teste de regressão trava tudo o que foi mostrado antes.

**O que não dá para mostrar com dados reais ainda (diga isso ao cliente):** não
existe modelo de pose treinado. A anotação real (US-06) não aconteceu, e o treino
exige uma GPU NVIDIA (US-07). Por isso, no US-07 e no US-08 a demonstração mostra
o planejamento, as recusas e os testes. No US-09 e no US-10, a série e a revisão
rodam de verdade sobre uma **pose simulada** a partir do vídeo real (B.12).

**Dois tipos de vídeo real.** Os vídeos de amostra (`$v1`, `$v2`: 15–20 s, 600×600)
servem ao Sprint 1, que precisa de dois trials da mesma câmera (rotação e recorte,
B.7 e B.8). O **vídeo completo** de um trial do LNBio (`$vc`: 6 min, 640×480, animal
1, aquisição, 23/06/2020) tem montagem própria e é o trial usado da B.9 em diante:
amostragem, pose, eventos e distância rodam sobre uma busca real de cerca de 3 min.
Nele aparecem a mão do experimentador (4 s), a caixa de partida sobre a plataforma
(até 81 s), a busca e a entrada no buraco de fuga (cerca de 268 s).

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
`develop` atualizado, com os cards do Sprint 2 já integrados).

```powershell
cd barnes-maze
```

**Faça commit de tudo antes da reunião.** Cada execução registra o commit e se
havia alterações não commitadas (US-27). Com o repositório sujo, todas as execuções
da demonstração aparecem como "não reproduzíveis", e o Cenário 4 do US-27 (B.14)
perde o contraste. O esperado aqui é a lista vazia:

```powershell
git status --short
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
$env:BARNES_DATABASE_URL = "postgresql://barnes:barnes@localhost:5433/barnes_demo"
```
```powershell
uv run barnes db migrate
```

Esperado: a lista das migrações aplicadas, da `0001` até a `0010_us18_deslocamento.sql`.

O banco de **testes** (`barnes_test`, criado pelo Docker na primeira subida) também
precisa das migrações, para que os testes de banco rodem na B.1 em vez de serem
pulados. Use a mesma porta da URL acima:

```powershell
uv run barnes db migrate --dsn postgresql://barnes:barnes@localhost:5433/barnes_test
```
```powershell
$env:BARNES_TEST_DATABASE_URL = "postgresql://barnes:barnes@localhost:5433/barnes_test"
```

Apague também os arquivos de uma demonstração anterior. Eles ficam em disco, não
no banco: os quadros exportados no US-06 (a B.9 recusa reamostrar um trial que já
tem quadros), os relatórios e a pose simulada do Sprint 2 (os comandos de
diagnóstico e de plano não sobrescrevem um relatório existente) e as séries de
pose da demonstração, além das saídas de eventos e da correlação da distância do
Sprint 3:

```powershell
Remove-Item -Recurse -Force data\demo_anotacao, data\pose\demo, data\demo_interim, data\demo_events, data\demo_validation -ErrorAction SilentlyContinue
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

O vídeo completo de um trial (6 min), usado da B.9 em diante:

```powershell
$vc = "data\raw\BM_Animal_1_Aquisicao_trial_2_23.06.2020.mp4"
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

Pastas do Sprint 2. Os relatórios de máquina, os planos de treino e a pose simulada
ficam em `$posedemo`. As séries de pose da demonstração ficam em `$interim`, fora da
`data\interim` do desenvolvimento, para não sobrescrever a série de um trial do
banco de desenvolvimento que tenha o mesmo número:

```powershell
$posedemo = "data\pose\demo"
```
```powershell
$interim = "data\demo_interim"
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

Esperado: nenhum teste falhando, `All checks passed!` e **3 testes pulados**, por
motivos que não são defeito:

- 2 exigem o SLEAP-NN instalado (extra `pose`, que só se instala na máquina NVIDIA
  de treino, US-07);
- 1 exige `AF_UNIX`, que o Windows não oferece (proteção offline da inferência, US-08).

Se aparecerem dezenas de pulados com `Requer BARNES_TEST_DATABASE_URL`, o banco de
testes não foi configurado: refaça a parte da A.2 sobre o `barnes_test`.

O que dizer: cada regra de negócio dos cards tem teste automático, e o código
segue um padrão verificado por ferramenta. Os casos que não dá para reproduzir
ao vivo (fps variável, erro < 3% com escala conhecida, ida e volta em todos os
buracos, treino e avaliação do modelo de pose) estão nos testes mostrados em cada
card abaixo.

### B.2 Cadastro do experimento

Ainda não existe comando para cadastrar usuário e experimento, então eles são
criados direto no banco:

```powershell
$user = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "INSERT INTO users (email, name) VALUES ('demo@lnbio.local', 'Demonstração') RETURNING id").Trim()
```
```powershell
$exp = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "INSERT INTO experiments (user_id, name) VALUES ($user, 'Experimento demonstração') RETURNING id").Trim()
```

O animal do experimento (1 experimento = 1 animal). Ele aparece no catálogo do
US-27 (B.14):

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "INSERT INTO subjects (experiment_id, name) VALUES ($exp, 'Camundongo demo')"
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

Depois do `Enter`, o terminal mostra quantos dos N buracos foram corrigidos
automaticamente para o buraco real detectado (ex. `16 de 20 buracos ajustados
automaticamente...`) — os que não tiverem um buraco real próximo o bastante
ficam na posição estimada pelo círculo, e exigiriam reabrir a janela e
arrastar à mão para corrigir.

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

**Montagem da câmera do vídeo completo.** O vídeo completo é de outra câmera
(640×480), então precisa de montagem própria. O quadro 0 mostra a plataforma vazia.

🖱️ Na janela, os mesmos passos de antes, com uma diferença: use como buraco de
referência o **buraco escuro de cima à direita** (é o alvo, com a caixa de fuga
embaixo) — arraste o centro até ele — e marque **o mesmo buraco** como alvo com o
botão direito. A tecla `h` encontra o anel dos buracos neste vídeo.

```powershell
uv run barnes maze create --experiment-id $exp --name "montagem completa" --reference-frame $vc --arena-diameter-cm $arena_cm --hole-diameter-cm $buraco_cm
```
```powershell
$mazec = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM maze_configs WHERE experiment_id = $exp AND name = 'montagem completa' ORDER BY id DESC LIMIT 1").Trim()
```

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

O vídeo completo, sem janela. O esperado é `640x480`, `9444` quadros, `377.71s`,
fps real `25.001` e **nenhum** aviso de fps variável:

```powershell
uv run barnes video load $vc --no-preview
```

O que dizer: este vídeo tem o padrão de B-frames do LNBio (intervalos alternando
~32 ms e ~48 ms, média exata de 25 fps). Ele era marcado como "fps variável" por
engano até 12/11/2026; a regra passou a comparar cada intervalo com o intervalo
médio. A linha `Intervalo útil: 4.40s ...` é discutida na B.6.

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

**Escala da montagem do vídeo completo.**

🖱️ Os mesmos 4 cliques (dois diâmetros da plataforma) e `Enter`, agora no vídeo
completo. O esperado é cerca de 0,197 cm/px (a plataforma tem uns 466 px de diâmetro):

```powershell
uv run barnes scale calibrate --video $vc --maze-config-id $mazec --length-1-cm $arena_cm --length-2-cm $arena_cm
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
$t1 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $maze AND day_number = 1 ORDER BY id DESC LIMIT 1").Trim()
```
```powershell
$t2 = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $maze AND day_number = 2 ORDER BY id DESC LIMIT 1").Trim()
```

**Trial do vídeo completo: a detecção automática erra, o recorte é manual.** Na
B.4, o vídeo completo mostrou `Intervalo útil: 4.40s (quadro 110) ... — detecção
automática`. Aos 4,4 s o que se move é a **mão do experimentador** colocando a
caixa de partida; o animal só é solto quando a caixa é levantada, aos 81,5 s, e
entra no buraco de fuga por volta de 268 s. O trial é gravado com o intervalo
ajustado à mão (Cenário 2), de 81,5 s a 270 s:

```powershell
uv run barnes video load $vc --experiment-id $exp --maze-config-id $mazec --day 1 --trial-in-day 2 --start-s 81.5 --end-s 270 --no-preview
```
```powershell
$tc = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT id FROM trials WHERE maze_config_id = $mazec ORDER BY id DESC LIMIT 1").Trim()
```

O esperado: `Intervalo útil: 81.50s (quadro 2038) a 270.00s (quadro 6750) — ajustado
manualmente.`

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

O que dizer, com transparência: nos vídeos de amostra o animal já começa solto, e o
recorte começa em 0 s. No vídeo completo, a heurística (primeiro movimento) dispara
com a mão do experimentador, 77 s antes da soltura real. Ela não serve para vídeos
com caixa de partida; nesses, o recorte é manual, e o ajuste fica registrado no
trial (`ajuste_manual = t` na auditoria acima).

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
O `execucao_id` é a execução registrada automaticamente junto com as métricas
(US-27 Cenário 1): o que ela guarda é mostrado na B.14.
Como o recorte do trial 1 começa em 0 s (veja a auditoria da B.6), o esperado é
`"samples_outside_interval": 0`. Se a detecção automática tiver marcado outro
início nesse vídeo, as amostras anteriores a ele ficam de fora, e é esse o
comportamento correto. `cobertura_pose` e `qualidade_pose` saem `null`: esses
trials não têm série de pose (`pose series`, US-09/US-10), e a trajetória da demo
vem de um CSV.

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

**O trial completo.** O `pose sample` recebe o vídeo, não o trial; sem recorte, ele
usaria a detecção automática (a mão, aos 4,4 s) e a caixa de partida preta seria
confundida com o animal. Por isso o intervalo do trial vai em quadros (2038 a 6750
= 81,5 s a 270 s, o mesmo gravado na B.6). Leva cerca de 30 s:

```powershell
uv run barnes pose sample --video $vc --maze-config-id $mazec --start-frame 2038 --end-frame 6750 --out $anot
```

O esperado: o animal encontrado em cerca de 99% dos quadros varridos, `borda` 30/30,
`buraco` 40/40 e `centro` com cerca de 18/30 e `FALTARAM quadros`. O que dizer: é o
comportamento real — o camundongo quase não atravessa o centro aberto da plataforma
(tigmotaxia). Faltam quadros de centro, e o aviso pede mais trials.

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

O esperado: cerca de 115 quadros (os 3 trials).

**Cenário 2 — cobertura por região.** Conta os quadros pelo centro do corpo
anotado, cada trial com a sua própria montagem (aqui, duas câmeras). O esperado é
`Montagem(ns) usada(s):` com os dois ids e `Cobertura OK: as três regiões têm
quadros anotados.`, com a proporção de cada região. Se o animal nunca passar por
alguma região, o comando **reprova** e diz qual.

```powershell
uv run barnes pose report --annotations $anot\anotacoes.csv --samples $anot
```

**Cenário 1 / RN03 — a divisão é por trial, nunca por quadro.** Com os 3 trials, fica
um trial inteiro em cada conjunto. O esperado é `treino 1 trial(s)`, `validacao 1
trial(s)` e `teste 1 trial(s)`, cada um com o número de quadros do seu trial:

```powershell
uv run barnes pose split --annotations $anot\anotacoes.csv --out $anot\divisao.csv
```
```powershell
uv run barnes pose check-split --manifest $anot\divisao.csv
```

O que dizer: a divisão é por trial, então os conjuntos ficam desbalanceados em
quadros (o trial completo tem 88; os de amostra, 12 e 15). Com menos de 3 trials o
sistema **recusa** em vez de dividir por quadro — coberto pelos testes do fim desta
seção.

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

### B.10 US-07 — Ambiente e treino do modelo de pose

O que dizer antes: o US-07 entrega o **ferramental** de treino: diagnóstico da
máquina, escolha do local de treino, pacote congelado dos dados anotados, treino
SLEAP com registro completo e versionamento dos pesos. O modelo em si **ainda
não foi treinado**. Faltam a anotação real (US-06) e uma máquina NVIDIA elegível.
Nada nesta seção é um modelo de verdade, e os rótulos simulados da B.9 não servem
para treinar.

**Diagnóstico da máquina (SCRUM-100).** Confere GPU NVIDIA (mínimo 4 GiB de
VRAM), RAM (mínimo 16 GB), driver e versões, e grava o relatório mesmo quando a
máquina é recusada:

```powershell
uv run barnes pose hardware --out $posedemo\hardware.json
```

Esperado numa máquina sem NVIDIA: o nome da máquina, a RAM e o motivo da recusa
(`nvidia-smi não encontrado nesta máquina.`), com saída de erro. Numa máquina
elegível, o esperado é `RAM/VRAM aprovadas`. Nesse caso, o plano abaixo escolhe
`grupo` direto e os passos de fallback não se aplicam: mostre-os pelos testes do
fim desta seção.

**Cenário 3 — sem GPU, o fallback é planejado e registrado, e nenhum vídeo sai do
laboratório.** A ordem de preferência é grupo → GPU institucional → Kaggle → Colab.
Cada plano é gravado num arquivo próprio, e nenhum arquivo é enviado para lugar
algum.

Disponibilidade da GPU institucional ainda não confirmada. O esperado é
`Plano: pending`, pedindo para confirmar. Disponibilidade desconhecida **não**
conta como indisponível:

```powershell
uv run barnes pose plan-training --report $posedemo\hardware.json --out $posedemo\plano-1.json
```

GPU institucional disponível. O esperado é `Plano: selected | local: institucional`:

```powershell
uv run barnes pose plan-training --report $posedemo\hardware.json --institutional sim --out $posedemo\plano-2.json
```

Sem GPU institucional, só sobra a nuvem, e a nuvem exige a resposta **D4**
favorável. Sem ela, o esperado é `Plano: blocked` e `Nuvem bloqueada: exige
resposta D4 favorável e sua referência.`:

```powershell
uv run barnes pose plan-training --report $posedemo\hardware.json --institutional nao --kaggle sim --out $posedemo\plano-3.json
```

Com uma referência de D4 (aqui **fictícia**, só para mostrar a regra; a D4 real
continua pendente), o esperado é `Plano: selected | local: kaggle`:

```powershell
uv run barnes pose plan-training --report $posedemo\hardware.json --institutional nao --kaggle sim --d4-reference "SIMULADO - so para a demonstracao" --out $posedemo\plano-4.json
```
```powershell
Get-Content $posedemo\plano-4.json
```

O que mostrar no arquivo: `"uploads_performed": false`,
`"allowed_cloud_data": "quadros_rotulados"` e a política `Nuvem: somente quadros
rotulados com D4 favorável; nunca vídeos.` (RN04). O sistema não cria conta nem
envia nada; a transferência, quando autorizada, é manual e leva só o pacote de
quadros rotulados.

**O treino exige GPU.** Numa máquina sem NVIDIA, o treino é recusado antes de
qualquer outra coisa, e nenhum diretório de modelo é criado. O esperado é
`Erro: Treino bloqueado: nvidia-smi não encontrado nesta máquina. ...`. Numa
máquina elegível, a recusa é por falta do pacote de dados, que aqui não existe:

```powershell
uv run barnes pose train --dataset $posedemo\sem-pacote
```

**Cenários 1 e 2 — treino concluído e reprodutível**, nos testes. Eles cobrem o
pacote congelado dos dados (`pose prepare-training`), um treino real de uma época
com o SLEAP-NN em CPU (pulado se o extra `pose` não estiver instalado), o
manifesto com hiperparâmetros, versão dos dados, ambiente, máquina e commit, os
pesos verificados por hash em `models/` e o registro em `execucao`:

```powershell
uv run pytest tests/pose/test_environment.py tests/pose/test_dataset.py tests/pose/test_training.py tests/pose/test_cli_training.py -v
```

O que mostrar no documento: `configs/pose/single_animal.yaml` (hiperparâmetros
iniciais da equipe) e, no [guia de treino e avaliação](pose-treino-avaliacao.md),
a seção "Treinar uma vez por montagem", com o que fica gravado em cada
`models/sleap-maze-<montagem>-<id>/`.

---

### B.11 US-08 — Avaliação por região e inferência local

O que dizer antes: avaliação e inferência estão implementadas, mas **dependem do
modelo do US-07**. Sem modelo, o erro real por região e a inferência sem rede na
máquina do laboratório não podem ser mostrados. O que dá para mostrar ao vivo é a
recusa de um modelo que não terminou de treinar. O resto está nos testes.

**Inferência recusa modelo incompleto.** Um treino interrompido não vira modelo.
Simule a pasta de um treino que parou no meio:

```powershell
New-Item -ItemType Directory -Force $posedemo\modelo-interrompido | Out-Null
```
```powershell
Set-Content -Path $posedemo\modelo-interrompido\manifest.json -Value '{"schema_version": 1, "status": "running"}' -Encoding ascii
```

O esperado é `Erro: Modelo local inválido: Modelo sem treino concluído ou
manifesto incompatível.`, sem ler o vídeo:

```powershell
uv run barnes pose infer --model $posedemo\modelo-interrompido --trial $t1
```

**Cenários 1, 2 e 3 — critério de meio corpo, erro por região e borda
reprovada.** O erro de cada ponto é dividido pelo comprimento do corpo anotado no
quadro (focinho até base da cauda). O aceite é estrito: abaixo de 0,5 para cada
ponto e no agregado, no global e em cada região (centro, borda e proximidade de
buraco). Se a borda reprovar, a avaliação reprova o card e grava localmente
`us06-borda.json`/`.md`, pedindo uma nova rodada de anotação em trials novos,
sem mexer no conjunto de teste:

```powershell
uv run pytest tests/pose/test_evaluation.py -v
```

**Cenário 4 — inferência local e sem rede, com tempo por trial.** A inferência lê
o vídeo em sequência (sem seek, por causa dos B-frames), confere hash, resolução e
montagem do trial, processa só o intervalo útil e registra o tempo. Durante o
treino e a inferência, conexões externas são bloqueadas:

```powershell
uv run pytest tests/pose/test_inference.py tests/pose/test_offline.py -v
```

O que dizer, com transparência: o bloqueio de rede é feito pelo próprio programa.
Ele não prova que a máquina do laboratório estava desconectada. A validação real
exige rodar `pose infer` na máquina do laboratório com a rede física desligada e
registrar máquina, operador, data e duração ([guia](pose-treino-avaliacao.md),
seção "Inferência por trial e validação sem rede").

---

### B.12 US-09 — Série de posição e orientação da cabeça

O que dizer antes: a série é gerada a partir do `pose.csv` que o `pose infer`
(US-08) produz. Como ainda não há modelo, esta seção usa uma **inferência
simulada**, no mesmo formato. O centro do corpo vem da segmentação por contraste
do US-06 (a mesma da amostragem), e focinho e base da cauda ficam no eixo do
movimento. Os pontos podem ficar um pouco fora do animal, e **isso precisa ser
dito ao cliente**. A simulação também injeta três falhas de pose, usadas no US-10
(B.13):

- focinho ausente por 3 quadros: lacuna curta, que será interpolada;
- focinho ausente por 15 quadros: lacuna longa, que será corrigida na revisão;
- base da cauda ausente por cerca de 7% do intervalo: lacuna longa, que será
  revisada sem correção.

**Inferência simulada** do trial completo (`$tc`). Lê os cerca de 4.700 quadros do
intervalo útil uma vez e leva cerca de 30 s. O camundongo preto sobre a plataforma
branca contrasta bem, então o centro do corpo segue o animal de verdade:

```powershell
$inf = "$posedemo\inferencia-simulada-t$tc"
```
```powershell
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
```

**Anote os quadros da lacuna longa do focinho**: a revisão da B.13 abre nela.

**Cenário 1 — série gerada.** Gera a série do trial completo a partir da inferência
(simulada). O comando confere se a inferência é do mesmo trial, do mesmo vídeo
(hash), da mesma montagem e com o mesmo fps, e converte para cm com a escala da
montagem (US-02):

```powershell
uv run barnes pose series --trial $tc --inference $inf --out $interim
```

O esperado: `Trajetória: data\demo_interim\trial_<id>.parquet | 4713 quadros, 15
sem pose válida | execução #...`. Também aparece a linha de cobertura do US-10
(cerca de 92,7%, `revisao_pendente`) e o aviso de 2 trechos sinalizados para revisão
(B.13): os 15 quadros do focinho e os cerca de 330 da base da cauda.

Para conferir o conteúdo do arquivo, guarde este leitor numa variável. Ele é
usado de novo na B.13:

```powershell
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
```
```powershell
$serie = "$interim\trial_$tc.parquet"
```
```powershell
$mostrar_serie | uv run python - $serie
```

O que mostrar:

- **uma linha por quadro do intervalo útil**, com `t_s` começando em 0 na soltura
  (US-03), posição em **cm** e θ em **graus** (Cenário 1);
- a convenção de θ: 0° aponta para a direita da imagem e cresce no sentido horário
  na tela, a mesma dos buracos (US-04);
- **Cenário 3 — quadro sem pose**: na lacuna longa do focinho, a linha existe com
  `nan`, `pose_valida = False` e `interpolado = False`. O quadro anterior não é
  repetido.

**A série fica registrada.** A execução (US-27) guarda o modelo usado (aqui
`simulado-demo`, o que deixa claro que a pose é simulada), o hash do `pose.csv`, a
escala, o intervalo e os parâmetros de tratamento do US-10:

```powershell
$exec_serie = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT cobertura_execucao_id FROM trials WHERE id = $tc").Trim()
```
```powershell
uv run barnes execution show $exec_serie
```

**A pose de um trial não serve para outro.** O esperado é `Erro: A inferência em
... é do trial #<tc>, não do #<t1>.`:

```powershell
uv run barnes pose series --trial $t1 --inference $inf --out $interim
```

**Cenário 2 — θ concorda com a direção do deslocamento**, nos testes, com
trajetórias retas nas 8 direções (erro < 1e-6° sem ruído; mediana ≤ 5° com ruído
de 1 px). Os testes também cobrem a conversão px→cm e o contrato do arquivo,
conferido na escrita e na leitura:

```powershell
uv run pytest tests/pose/test_series.py tests/pose/test_trajectory.py tests/pose/test_series_from_inference.py -v
```

O que mostrar no documento: `docs/contrato-trajetoria.md`, o contrato do arquivo
que o Épico D (eventos por buraco) vai ler.

---

### B.13 US-10 — Suavização, interpolação e revisão de falhas de pose

O que dizer antes: o `pose series` da B.12 já tratou a pose. Ele aplica as
correções manuais registradas, suaviza com mediana móvel, interpola as lacunas
curtas e sinaliza as longas para revisão humana. Os limites estão em
`configs/default.yaml` e são **propostos pelo grupo**:

```powershell
Select-String -Path configs\default.yaml -Pattern "cobertura_minima|lacuna_curta_max_quadros|metodo|janela_quadros"
```

Lacuna curta: até 5 quadros (0,2 s a 25 fps) com o ponto presente antes e depois.
Lacuna longa: qualquer uma maior, ou que toque o início ou o fim do intervalo.
Cobertura: fração dos quadros com focinho, centro e base da cauda, contando os
interpolados e os corrigidos. Critério do projeto: ≥ 0,98.

**Cenário 1 — lacuna curta interpolada, sem pedir revisão.** Já apareceu na saída
da B.12: as 3 linhas da lacuna curta estão preenchidas com `interpolado = True`, e
a lista de trechos sinalizados traz só as duas lacunas longas.

**Cenário 2 — lacuna longa: a revisão vai direto ao trecho, permite a correção e
registra a intervenção.**

🖱️ Na janela:
1. ela abre **direto no trecho 1** (o focinho, nos quadros anotados na B.12), sem
   passar pelo resto do vídeo. O cabeçalho mostra `Trecho 1/2 (pendente)`, os
   quadros, o ponto que falta e o ponto ativo. Os círculos vazados são os pontos
   que a série já tem;
2. **`d`** 5 vezes (6º quadro do trecho) e **clique no focinho** do animal;
3. **`d`** mais 5 vezes (11º quadro) e **clique no focinho** de novo;
4. **`Enter`**: dá o trecho 1 por revisado, e a janela pula para o trecho 2 (base
   da cauda);
5. diga que, neste trecho, a cauda está encoberta, e aperte **`Enter`** sem marcar
   nada;
6. **`s`** salva e fecha.

`a`/`d` andam um quadro, `n`/`p` trocam de trecho, `1`/`2`/`3` escolhem o ponto, e o
botão direito ou `Backspace` desfaz. `Esc` cancela **sem gravar nada**.

```powershell
uv run barnes pose review --trial $tc
```

O esperado: `Revisão registrada na execução #...: 2 ponto(s) corrigido(s), 2
trecho(s) dado(s) por revisado(s).`, a nova cobertura (cerca de 93%) e o aviso
`QUALIDADE INSUFICIENTE` (Cenário 3, abaixo).

O que dizer: não foi preciso marcar os 15 quadros. Com duas marcações, a lacuna
virou três lacunas de até 5 quadros, e essas foram interpoladas quando a série foi
regenerada. Confira:

```powershell
$mostrar_serie | uv run python - $serie
```

O esperado: não há mais quadro sem focinho, e a lacuna do focinho saiu da lista de
trechos sinalizados, porque foi preenchida. Só a base da cauda continua ausente, num
trecho marcado como `revisado`.

**A intervenção fica registrada (RN05).** Uma execução própria guarda os trechos
revisados, o número de correções, o usuário do sistema e a nova cobertura. A
tabela `correcao_pose` guarda cada ponto marcado:

```powershell
$rev = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT cobertura_execucao_id FROM trials WHERE id = $tc").Trim()
```
```powershell
uv run barnes execution show $rev
```
```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT id, execucao_id, quadro, ponto, round(x_px::numeric,1) AS x_px, round(y_px::numeric,1) AS y_px FROM correcao_pose WHERE trial_id = $tc ORDER BY id"
```

O que mostrar: `"comando": "pose review"`, `trechos_revisados`,
`"correcoes_novas": 2` e, em `metadata.qualidade_pose`, a cobertura e os trechos.
Uma correção não se edita. O esperado é `ERROR: Correções de pose são imutáveis;
registre uma nova revisão.`:

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "UPDATE correcao_pose SET x_px = 0 WHERE trial_id = $tc"
```

**Cenário 3 — cobertura abaixo do critério: a marcação vai junto do trial nas
saídas.** No catálogo, a cobertura do trial completo aparece com a qualidade
`INSUFICIENTE`:

```powershell
uv run barnes catalog list
```

Nas métricas, cada resultado leva `cobertura_pose` e `"qualidade_pose":
"insuficiente"` — aparece na distância e velocidade da B.17.

A marcação não é gravada como um "sim/não" à parte: ela é calculada da cobertura e
do relatório da execução que a mediu, numa visão do banco. Assim, ela nunca fica
diferente da cobertura:

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT * FROM qualidade_pose WHERE trial_id = $tc"
```

**Regenerar não perde a revisão.** A série é sempre refeita a partir do
`pose.csv`, com todas as correções do banco. Gerar de novo dá a mesma cobertura,
sem trecho pendente:

```powershell
uv run barnes pose series --trial $tc --inference $inf --out $interim
```

O esperado na revisão é `Nenhum trecho pendente de revisão no trial #...`:

```powershell
uv run barnes pose review --trial $tc
```

**RN07 (fps instável) e os demais casos**, nos testes. Os vídeos da demonstração
têm fps constante. Com fps variável, o relatório de qualidade leva a ressalva de
que a interpolação é menos exata:

```powershell
uv run pytest tests/pose/test_quality.py tests/pose/test_review_ui.py tests/db/test_pose_corrections.py -v
```

O que mostrar no documento: a seção "Pós-processamento (US-10)" de
`docs/contrato-trajetoria.md` e a §4.7 do manual (teclas da revisão).

---

### B.14 US-27 — Proveniência das execuções e catálogo de trials

**Cenários 1 e 2 — toda execução é registrada, com o suficiente para reproduzir.**
O histórico de métricas do trial 1 traz várias linhas (antes e depois da
recalibração da B.8), cada uma com o seu `execucao_id`:

```powershell
uv run barnes metrics executions --trial $t1 --history
```
```powershell
$exec = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT execucao_id FROM trial_results WHERE trial_id = $t1 ORDER BY id DESC LIMIT 1").Trim()
```
```powershell
uv run barnes execution show $exec
```

O que mostrar: `model_id` (nulo, porque estas métricas vêm de uma trajetória CSV,
sem modelo de pose; nas execuções da B.12 e da B.13 aparece `simulado-demo`), os
`limiares` vigentes (o `configs/default.yaml` inteiro, com o hash), os `parametros`
(vídeo, hash da trajetória, escala, intervalo), o `git_commit`, `git_dirty: false`,
a data e `"reproduzivel": true`. Para reproduzir: fazer checkout do commit,
restaurar os limiares e repetir o comando com os parâmetros.

Todas as execuções do trial 1 e do trial completo, de todas as etapas (métricas da
B.8; série e revisão da B.12/B.13):

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT id, trial_id, kind, coalesce(model_id, '-') AS modelo, parametros->>'comando' AS comando, git_dirty AS sujo, recorded_at::timestamp(0) AS registrada FROM execucao WHERE trial_id IN ($t1, $tc) ORDER BY id"
```

**RN02 — métrica sem execução é erro de esquema.** O esperado é `ERROR: null
value in column "execucao_id" ... violates not-null constraint`:

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "INSERT INTO trial_results (trial_id, distance_cm) VALUES ($t1, 1.0)"
```

**RN03 — catálogo.** Trial, animal, sessão (o dia), fase, ordem no dia, situação,
cobertura e qualidade de pose, fps e situação do arquivo de vídeo:

```powershell
uv run barnes catalog list
```

O que mostrar: o animal `Camundongo demo` (B.2) e as situações `processado` (trials
1 e 2, se o trial 2 tiver métricas) e `carregado` (trial da montagem sem escala e,
até a B.17, o trial completo). Só o trial completo tem cobertura e qualidade (B.13).
A sessão vem de uma visão derivada dos trials:

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT * FROM sessao WHERE experiment_id = $exp"
```

**Cenário 3 — vídeo movido ou substituído é sinalizado, com o trial.**

Vídeo movido e renomeado:

```powershell
New-Item -ItemType Directory -Force data\raw\movidos | Out-Null
```
```powershell
Move-Item $v1 data\raw\movidos\renomeado.mp4
```

O esperado é o aviso `Divergência no trial #<t1>: vídeo movido ou renomeado para
data\raw\movidos\renomeado.mp4.` e a coluna **arquivo** com `movido`:

```powershell
uv run barnes catalog list --procurar-em data\raw\movidos
```

Reprocessar com o arquivo no lugar novo funciona, porque o conteúdo (hash) é o
mesmo. O comando avisa, e o caminho novo fica registrado na execução:

```powershell
uv run barnes metrics process --video data\raw\movidos\renomeado.mp4 --trial $t1 --trajectory data\interim\traj_demo.csv
```

Devolva o vídeo ao lugar:

```powershell
Move-Item data\raw\movidos\renomeado.mp4 $v1
```

Vídeo substituído por outro conteúdo no mesmo caminho. O vídeo sintético é
copiado antes, para ser restaurado depois:

```powershell
Copy-Item $vs "$vs.bak"
```
```powershell
Copy-Item data\raw\corrompido.mp4 $vs -Force
```

O esperado é `Divergência no trial #<t0>: conteúdo de data\raw\sintetico_soltura.mp4
difere do catalogado.`:

```powershell
uv run barnes catalog list
```

Restaure o vídeo e confira tudo pelo conteúdo completo. Esta opção relê cada
vídeo e é mais lenta. O esperado é `ok` em todos os trials:

```powershell
Move-Item "$vs.bak" $vs -Force
```
```powershell
uv run barnes catalog list --verificar-hash
```

A recusa de reprocessar um vídeo substituído está nos testes do fim desta seção.

**Cenário 4 — repositório com alterações não commitadas.** Crie um arquivo novo,
não commitado, na pasta do projeto:

```powershell
Set-Content -Path demo_alteracao_nao_commitada.txt -Value "simula uma alteracao nao commitada" -Encoding utf8
```

O esperado é o aviso `execução #... registrada com repositório sujo (alterações
não commitadas) — o resultado não é reproduzível pelo commit.`:

```powershell
uv run barnes metrics process --video $v1 --trial $t1 --trajectory data\interim\traj_demo.csv
```
```powershell
$sujo = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT max(id) FROM execucao WHERE trial_id = $t1").Trim()
```
```powershell
uv run barnes execution show $sujo
```

O esperado: `"git_dirty": true` e `"reproduzivel": false`. Apague o arquivo:

```powershell
Remove-Item demo_alteracao_nao_commitada.txt
```

**Testes do US-27**: métrica e evento órfãos recusados pelo banco, execução
imutável, catálogo, arquivo movido ou alterado, e repositório sujo ou sem git:

```powershell
uv run pytest tests/db/test_us27_schema.py tests/db/test_catalog.py tests/test_provenance.py tests/io/test_verify_video.py -v
```

O que dizer sobre o banco do laboratório: a decisão (SCRUM-148) é instalar o
PostgreSQL nativo na máquina do laboratório (manual, §2.2.2). A demonstração usa o
Docker só por conveniência.

---

### B.15 US-11 — Detecção do evento de descoberta (D)

O que dizer antes: a descoberta (D) é o primeiro quadro em que o focinho fica
perto do buraco **e** a cabeça está orientada para ele — os dois limiares vêm
de `configs/default.yaml`, nunca do código (RN02). O cálculo lê só a
trajetória já tratada da B.12/B.13 (`$serie`), nunca o vídeo: mudar um limiar
e rodar de novo não reprocessa nada (RN04).

**Os limiares são PROVISÓRIOS — diga isso ao cliente.** Sem contato com o
laboratório, C1 (G3) não fecha; os valores abaixo são uma faixa comum de rastreamento
comportamental de roedores, sem citação verificada
(`docs/definicoes-metricas.md`, seção 1):

```powershell
Select-String -Path configs\default.yaml -Pattern "encontrar:|distancia_cm|angulo_graus|calibrado_contra_anotacao"
```

**Cenário 1 — descoberta detectada.** Roda sobre a série já tratada do trial
completo (B.13, sem trechos pendentes):

```powershell
uv run barnes events discover --trial $tc
```

O esperado: uma linha por buraco cujo focinho chegou a menos de 3 cm,
orientado a menos de 30° da direção do buraco — o primeiro quadro que
satisfez os dois ao mesmo tempo. No ensaio de 12/11/2026 foram cerca de 12 buracos
descobertos; o primeiro aos ~6,6 s depois da soltura e o **alvo (buraco 0) aos
~157 s**. Os números variam um pouco com a montagem marcada na B.3. Os buracos que
o animal contornou pela borda sem virar a cabeça não aparecem (**Cenário 2**).

**Cenário 3 — recálculo sem reprocessar o vídeo.** Prove que o vídeo nem
precisa estar no lugar: mova-o e rode de novo. O comando usa só `$serie` e o
hash já catalogado, nunca lê `$vc`:

```powershell
Move-Item $vc data\raw\movidos\completo.mp4
```
```powershell
uv run barnes events discover --trial $tc
```

O esperado: o mesmo resultado de antes, sem nenhum erro — ao contrário do
`metrics process` (B.14), que exige o vídeo para conferir a resolução. Devolva
o vídeo ao lugar:

```powershell
Move-Item data\raw\movidos\completo.mp4 $vc
```

**O evento fica registrado, ligado ao buraco e à execução que o gerou:**

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT h.hole_number, e.tipo, e.quadro, round(e.t_s::numeric,2) AS t_s, round(e.distancia_cm::numeric,2) AS distancia_cm, round(e.angulo_deg::numeric,1) AS angulo_deg FROM evento_buraco e JOIN holes h ON h.id = e.hole_id WHERE e.trial_id = $tc ORDER BY e.t_s"
```
```powershell
$exec_evt = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT max(id) FROM execucao WHERE trial_id = $tc AND parametros->>'comando' = 'events discover'").Trim()
```
```powershell
uv run barnes execution show $exec_evt
```

O que mostrar: `"kind": "processamento"`, os `limiares` vigentes (o
`configs/default.yaml` inteiro, com o aviso de que são provisórios dentro
dele) e os `parametros` com `distancia_cm`/`angulo_graus` efetivamente usados.

**Recalcular com outro limiar, sem tocar no vídeo nem no Parquet.** Um YAML à
parte, só para este teste, com limiares bem mais largos:

```powershell
Set-Content -Path $interim\limiares_teste.yaml -Value "encontrar:","  distancia_cm: 20","  angulo_graus: 90" -Encoding utf8
```
```powershell
uv run barnes events discover --trial $tc --config $interim\limiares_teste.yaml
```

O esperado: a mesma lista de antes ou mais buracos — o limiar maior encontra
mais cedo e com mais tolerância. As duas execuções ficam lado a lado,
consultáveis, sem o vídeo ter sido reaberto:

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT execucao_id, hole_id, quadro, t_s FROM evento_buraco WHERE trial_id = $tc ORDER BY execucao_id, hole_id"
```

**Testes do US-11**: carregamento dos limiares (recusa `null`/fora de faixa),
cálculo de distância/ângulo por quadro (Cenário 1/2, RN03) e a prova de que o
recálculo nunca abre o vídeo:

```powershell
uv run pytest tests/events/test_discovery.py tests/db/test_maze_configs.py -v
```

O que mostrar no documento: a nota da US-11 em `docs/definicoes-metricas.md`
(seção 1, linhas 1-2) — os limiares continuam provisórios: sem contato com o
laboratório, C1 não é calibrado.

---

### B.16 US-13/US-14/US-15 — Entrada, dwell e sequência de visitação (e US-12 bloqueada)

O que dizer antes: a descoberta (D, B.15) é a cabeça perto e virada para o buraco;
a **entrada** (E) é o focinho dentro do buraco por um tempo mínimo. A diferença
D→E é a hesitação que o `barnes_maze.py` modela (`delta_latency`/`delta_distance`).
Tudo sai da série tratada (`$serie`), sem abrir o vídeo.

**Os limiares são decisão da equipe, não do laboratório — diga isso ao cliente.**
Não houve contato com o LNBio; os valores foram aprovados pela equipe em 12/11/2026
e estão marcados no YAML (`docs/decisoes-sem-laboratorio.md`):

```powershell
Select-String -Path configs\default.yaml -Pattern "versao_definicoes|raio_fator|duracao_minima_s: 0|tempo_limite_s|criterio:"
```

O esperado: `versao_definicoes: decisoes-equipe-2026-11-12-sem-G3`, entrada com
`raio_fator: 1.0` e `duracao_minima_s: 0.2`, tempo limite de 180 s e erro =
qualquer buraco incorreto.

A migração `0009` (detalhes da entrada) precisa estar aplicada:

```powershell
uv run barnes db migrate
```

**US-13 + US-14 — entradas, hesitação e dwell.**

```powershell
uv run barnes events enter --trial $tc --out data\demo_events
```

O esperado: `Execução #N: K entrada(s). Saída: data\demo_events\entry-...`, com K por
volta de 37 no ensaio. Código de saída **2** não é falha do comando: indica
inconsistências registradas — no ensaio, 2 buracos em que a entrada veio antes da
descoberta (`descoberta D posterior à entrada E`), efeito do focinho simulado, que
fica sempre à frente do corpo. Elas aparecem no terminal como `Inconsistência: ...`
e ficam gravadas, nunca escondidas.

```powershell
$entrada = (Get-ChildItem data\demo_events -Directory -Filter entry-* | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
```
```powershell
Import-Csv "$entrada\entries.csv" | Format-Table hole_number_platform, t_s, discovery_t_s, delta_latency, delta_distance, dwell_s, dwell_interpolado, qualidade_pose
```

O que mostrar: uma linha por entrada (reentradas no mesmo buraco têm linha
própria); `delta_latency` (s) e `delta_distance` (cm) são a hesitação D→E; `dwell_s` é
quanto tempo o focinho ficou no buraco (US-14) e `dwell_interpolado` diz se algum
quadro desse trecho veio da interpolação da US-10. No ensaio, a **primeira entrada no
alvo** (buraco 0) veio aos ~161 s, 4 s depois da descoberta, com dwell de 1,8 s; o
animal volta ao alvo várias vezes antes de entrar de vez na caixa de fuga. Toques
com menos de 0,2 s não viram entrada.

O que dizer sobre a latência (US-16, sem comando): pela regra da equipe, a entrada
conta a partir do focinho no buraco por 0,2 s, então este trial **não** é censurado
(161 s < 180 s), embora o animal só suma na caixa de fuga aos ~187 s da soltura.

**US-15 — sequência de visitação**, montada só a partir das entradas gravadas, no
referencial da sala:

```powershell
uv run barnes events sequence --trial $tc --out data\demo_events
```
```powershell
$sequencia = (Get-ChildItem data\demo_events -Directory -Filter sequence-* | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
```
```powershell
Import-Csv "$sequencia\sequencia.csv" | Format-Table ordem, buraco_platform, angulo_deg_room, t_descoberta_s, t_entrada_s, dwell_s, alvo
```

O que mostrar: a ordem cronológica das checagens, cada buraco com o ângulo fixo na
sala (`_room`, US-05) e a marca do alvo. É a fonte única da contagem de erros (US-17)
e da classificação de estratégia (US-20).

**A execução registra os limiares usados** — inclusive a marca de decisão da equipe:

```powershell
$exec_ent = (docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -q -t -A -c "SELECT max(id) FROM execucao WHERE trial_id = $tc AND parametros->>'comando' = 'events enter'").Trim()
```
```powershell
uv run barnes execution show $exec_ent
```

O que mostrar: em `limiares`, o `versao_definicoes` e a seção `entrar` com os valores
da equipe. Qualquer número gerado com esses limiares é rastreável até a decisão.

**US-12 — calibração contra anotação manual: bloqueada.** Sem anotação de um
observador (D3), a rodada é registrada como bloqueada, sem inventar referência:

```powershell
uv run barnes events calibrate --trial $tc --out data\demo_events\calibracao
```

O esperado: `Bloqueado por D3: anotação não entregue.` e código de saída 2.

**US-16 e US-17 — latência com censura e contagem de erros.** Estão implementadas e
testadas, mas ainda **não têm comando** de linha de comando; mostre pelos testes:

```powershell
uv run pytest tests/metrics/test_latency.py tests/metrics/test_errors.py tests/events/test_sequence.py -v
```

O que dizer: `primary_*`/`total_*` com censura em 180 s (US-16) e
`total_errors`/`primary_errors` a partir da sequência (US-17) já são calculados pelo
código; falta o comando que os gera a partir de um trial gravado, e a exportação
`trials.csv` é a US-25.

---

### B.17 US-18 — Distância total e velocidade média

O que dizer antes: uma distância em cm e uma velocidade média em cm/s **por trial**,
calculadas a partir da série tratada da B.12/B.13 (`$serie`), nunca do vídeo. As
velocidades por fase (`primary_speed` etc.) não são calculadas aqui, porque o
`barnes_maze.py` do laboratório as deriva do próprio `trials.csv` (decisão da equipe,
`docs/decisoes-sem-laboratorio.md` §3).

A migração `0010` precisa estar aplicada no banco da demonstração:

```powershell
uv run barnes db migrate
```

**Cenário 1 — uma distância e uma velocidade por trial.** O trial completo já tem a
série revisada (B.13). No ensaio: cerca de **1.107 cm (11 m) em 188 s, 5,9 cm/s** —
velocidade típica de camundongo explorando:

```powershell
uv run barnes metrics displacement --trial $tc
```

O que mostrar no JSON:

- `distance_cm` e `mean_speed_cm_s`;
- `duration_s` (primeiro ao último quadro com o centro do corpo) ao lado de
  `interval_duration_s`;
- `interpolated_fraction`: as lacunas curtas que a B.13 interpolou entram no cálculo e
  aparecem aqui;
- `colunas_exportacao`, as quatro colunas que a US-25 vai levar ao `trials.csv`.

Se a simulação deixou o centro do corpo ausente numa borda, o aviso no terminal diz
quanto tempo ficou fora da velocidade.

**Prova de que o vídeo não é lido.** Mova o vídeo e rode de novo. O resultado é o
mesmo, sem erro:

```powershell
Move-Item $vc data\raw\movidos\completo.mp4
```
```powershell
uv run barnes metrics displacement --trial $tc
```
```powershell
Move-Item data\raw\movidos\completo.mp4 $vc
```

**O resultado fica gravado com a execução que o gerou** (uma linha por execução, US-27):

```powershell
docker exec barnes-maze-postgres-1 psql -U barnes -d barnes_demo -c "SELECT tr.execucao_id, round(tr.distance_cm::numeric,2) AS distancia_cm, round(tr.speed_mean_cm::numeric,2) AS velocidade_cm_s, round(tr.interpolated_fraction::numeric,3) AS fracao_interpolada, t.fps_is_variable AS ressalva_velocidade FROM trial_results tr JOIN trials t ON t.id = tr.trial_id WHERE tr.trial_id = $tc ORDER BY tr.execucao_id"
```

**Cenário 2 — correlação com a medida manual (r ≥ 0,95): bloqueado.** Não existe
medida manual de distância. A ferramenta registra a rodada como bloqueada e sai com
código 2:

```powershell
uv run barnes metrics distance-validate --saida data\demo_validation
```

O que dizer: a lista do que falta para medir está em `docs/definicoes-metricas.md`
§4.3 (quem mede, método, quais trials, inferência real).

**Cenário 3 — fps variável** e os demais casos (borda sem pose, lacuna atravessada,
ausência nunca vira zero, correlação aprovada/reprovada) estão cobertos por teste. Os
vídeos da demonstração não têm fps variável:

```powershell
uv run pytest tests/metrics/test_displacement.py tests/metrics/test_validation.py tests/metrics/test_cli_metrics.py tests/metrics/test_cli_metrics_postgres.py -v
```

### B.18 US-28 — Trial de referência e teste de regressão

O que mostrar: um vídeo curto versionado no repositório (`tests/fixtures/trial_referencia.mp4`)
e um arquivo com o valor esperado de cada métrica (`tests/fixtures/trial_referencia_esperado.yaml`).
O teste roda o pipeline inteiro sobre esse vídeo e falha se qualquer métrica mudar.

O que dizer: o vídeo é **sintético**. A trajetória é conhecida de antemão e injetada como
pose, porque não há modelo de pose treinado no repositório. O teste protege o cálculo
(descoberta, entrada, dwell, sequência, erros, latências, distância e velocidade), não a
qualidade da pose.

**Cenário 1 — pipeline íntegro.** Dez verificações, em cerca de 1,5 s:

```powershell
uv run pytest tests/test_us28_trial_referencia.py -v
```

**Cenário 2 — detecção de regressão.** Simule uma mudança que altera a contagem de erros:
guarde uma cópia do esperado, troque `total_errors: 1` por `2` e rode o teste. Ele deve falhar
dizendo `erros.total_errors: esperado 2, obtido 1`:

```powershell
Copy-Item tests\fixtures\trial_referencia_esperado.yaml $env:TEMP\esperado_us28.bak
@'
from pathlib import Path
p = Path("tests/fixtures/trial_referencia_esperado.yaml")
p.write_text(p.read_text(encoding="utf-8").replace("total_errors: 1", "total_errors: 2"), encoding="utf-8")
'@ | uv run python -
uv run pytest tests/test_us28_trial_referencia.py -q --tb=short
```

Restaure o arquivo **antes de continuar** e confira que o teste volta a passar:

```powershell
Copy-Item $env:TEMP\esperado_us28.bak tests\fixtures\trial_referencia_esperado.yaml -Force
uv run pytest tests/test_us28_trial_referencia.py -q
```

**Cenário 3 — atualização legítima do esperado.** É regra de processo: o commit que muda
o YAML diz qual métrica mudou, por quê e qual decisão motivou a mudança (README, seção
US-28). Exemplo real: a integração da US-18 acrescentou a seção `deslocamento` ao esperado.

## Parte C — Encerramento

Volte o terminal para o banco de desenvolvimento:

```powershell
Remove-Item Env:BARNES_DATABASE_URL, Env:BARNES_TEST_DATABASE_URL
```

Confira que os vídeos movidos na B.14 (`$v1`) e na B.15 e na B.17 (`$vc`) voltaram ao
lugar, que o arquivo de "alteração não commitada" foi apagado e que o esperado da
B.18 foi restaurado (`tests/fixtures` não aparece na lista). O esperado é `True`
duas vezes e a lista vazia:

```powershell
Test-Path $v1, $vc
```
```powershell
git status --short
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
| US-01 | fps variável | Por decisão do grupo, o sistema só avisa e não corrige. Coberto por teste; não há vídeo assim no acervo. O vídeo completo era marcado como variável por engano (padrão de B-frames com grupos de tamanhos diferentes); a regra foi corrigida em 12/11/2026 (B.4). |
| US-03 | Soltura em vídeo com caixa de partida | No vídeo completo, a detecção automática dispara com a mão do experimentador (4,4 s), 77 s antes da soltura real; o recorte é manual (B.6). O `pose sample` recebe o vídeo, não o trial, e precisa do intervalo em quadros (B.9). |
| US-02 | Mensagem do bloqueio sem escala | O card pede que a mensagem indique **o comando** para calibrar. Hoje ela diz que a montagem exige calibração, mas não cita o `barnes scale calibrate`. |
| US-02 / US-04 | Medidas físicas (B2) | A demonstração usa 92 cm de plataforma e 5 cm de buraco, que são valores típicos. Sem acesso ao aparato, as distâncias ficam condicionadas a uma dimensão assumida (decisão da equipe, `docs/decisoes-sem-laboratorio.md` §12). Um fator de escala não muda os hazard ratios. |
| US-03 | Detecção da soltura | Funciona no vídeo sintético. Nos vídeos de amostra o animal já começa solto; a equipe trata o início do vídeo como S (`docs/decisoes-sem-laboratorio.md` §2). |
| US-05 | Buraco físico de referência | Decisão da equipe: escolhido visualmente por quem monta a configuração, sempre o mesmo buraco físico (`docs/decisoes-sem-laboratorio.md` §1). |
| US-05 | B4: rotação | "Não rotaciona" é **suposição da equipe**, não resposta do LNBio (§13 do documento de decisões). O padrão 0° está no `--rotation-deg` do `video load`. |
| US-05 | Câmera deslocada entre dias | **Não é detectada automaticamente.** O procedimento é criar uma montagem nova e recalibrar a escala (manual, seção 3.7). Só um vídeo com resolução diferente é recusado automaticamente. |
| US-06 | Rodada de anotação | O ferramental está pronto; a anotação na B.9 é simulada. A rodada real depende dos 3 trials de G1 e da resposta D4 (uso dos quadros e CEUA). |
| US-04 | Raio do buraco | É ajustado a olho na janela (`[`/`]`). Não sai do diâmetro em cm, porque a escala só é calibrada depois da montagem existir. |
| US-07 | Modelo treinado | Ferramental pronto (diagnóstico, plano, pacote de dados, treino, registro). Falta o treino real: depende da anotação real (US-06), de uma máquina NVIDIA elegível (só esta máquina foi inventariada; faltam as dos outros integrantes) e, se for preciso usar nuvem, da D4. |
| US-07 | GPU institucional (D2) | Decisão da equipe: o treino roda nas máquinas da equipe; a GPU institucional deixou de ser pendência. O plano da B.10 continua `pending` até haver máquina NVIDIA elegível. |
| US-08 | Avaliação real por região | Critério e relatório por região implementados e testados com dados sintéticos. O erro real depende do modelo do US-07. |
| US-08 | Inferência offline no laboratório | Fluxo local implementado. Falta a validação na máquina do laboratório com a rede física desligada, com o registro de máquina, operador e duração. |
| US-09 | Série dos 3 trials representativos (SCRUM-123) | A série é gerada e conferida pelo contrato, mas nesta demonstração a pose é **simulada**. Falta gerá-la com o modelo real para os 3 trials de G1. |
| US-10 | Limites de tratamento da pose | Lacuna curta de 5 quadros (0,2 s), mediana de 5 quadros e cobertura mínima de 0,98: decisão da equipe (`docs/decisoes-sem-laboratorio.md` §15). |
| US-10 | fps instável (RN07) | A US-01 detecta fps variável por trial, não por trecho. A ressalva vale para o trial inteiro. |
| US-11 | Limiares de descoberta (G3, C1) | Implementado e testado; `encontrar.distancia_cm`/`angulo_graus` (3 cm / 30°) continuam **provisórios** e não calibrados. Sem contato com o laboratório, G3 não fecha; ver `docs/definicoes-metricas.md`. |
| US-18 | Velocidades por fase (SCRUM-223) | O `barnes_maze.py` deriva `primary/decision/total_speed` das distâncias e latências; decisão da equipe: `trials.csv` sem colunas de velocidade, probe de 90 s (§3 e §11 do documento de decisões). |
| US-18 | Aceite r ≥ 0,95 (SCRUM-225) | Ferramenta pronta; não há medida manual de distância. Mantido como limitação declarada (`docs/decisoes-sem-laboratorio.md` §5). |
| US-13 / US-16 / US-18 / US-17 | Limiares de entrada, tempo limite, erro e ponto do corpo | Decisões da equipe sem G3, em `configs/default.yaml` (`versao_definicoes: decisoes-equipe-2026-11-12-sem-G3`): entrada de 0,2 s, tempo limite de 180 s, erro = qualquer buraco incorreto, distâncias pelo centro do corpo. |
| US-12 / US-13 / US-15 / US-16 / US-17 / US-18 / US-21 | Comparação com anotação manual | **Pulada.** Não há anotação manual de Barnes maze, nem do laboratório nem pública (busca de 12/11/2026, `docs/decisoes-sem-laboratorio.md` §5.1). As ferramentas (`events calibrate`, `compare_sequence`, `metrics distance-validate`) estão prontas caso uma anotação apareça. |
| US-16 / US-17 | Latência, censura e erros | Calculados e testados (B.16, pelos testes), mas ainda sem comando que os gere de um trial gravado; a exportação `trials.csv` é a US-25. |
| US-28 | Trial de referência e teste de regressão | Implementado sobre um vídeo **sintético** (B.18); não exercita lacunas de pose, censura nem fps variável. O "teste obrigatório antes de merge" é regra de processo: o repositório não tem CI. |
| US-27 | Banco no laboratório | Decidido: PostgreSQL nativo na máquina do laboratório (SCRUM-148, manual §2.2.2). A instalação lá ainda não foi feita. |
| Geral | Métricas a partir da pose | A distância e a velocidade média já saem da série de pose (US-18, B.17). O `metrics process` da US-02 (B.8) continua lendo a trajetória de exemplo em CSV. |
| Geral | Cadastro de usuário, experimento e animal | Ainda não há comando nem tela; nesta demonstração ele é feito direto no banco. |

## Se algo der errado

| Sintoma | Solução |
|---|---|
| `... is not recognized as the name of a cmdlet` | O comando foi escrito com a sintaxe do bash. Use `$env:VAR = "..."` em linha separada. |
| Comandos dizem que `BARNES_DATABASE_URL` não está definida | O terminal foi trocado. Repita o `$env:BARNES_DATABASE_URL = ...` da A.2 e as variáveis da A.3 e A.4. |
| `$exp`, `$maze`, `$mazec`, `$t1`, `$t2` ou `$tc` vazios | Rode de novo o comando que define a variável e confira com `"$exp $maze $mazec $t1 $t2 $tc"`. |
| Erro de duplicado na gravação dos trials (B.6) | O banco já tinha esses vídeos. Refaça a A.2 para começar com o banco limpo. |
| `Got unexpected extra argument(s)` num comando com `$maze`, `$t1` etc. | A variável ficou com vários ids (por exemplo, o `maze create` foi rodado mais de uma vez; `Esc`/`q` salvam). Rode de novo o comando que define a variável, que agora pega o mais recente, e confira com `"$maze"`. |
| `No module named 'tests.io.test_trim'` (A.3) | Comando antigo do roteiro. Use o da A.3, que importa `test_trim` pelo caminho `tests/io`. |
| `pose sample` recusa com "--overwrite" no primeiro uso (B.9) | Sobraram quadros de um ensaio anterior. Rode o `Remove-Item` da A.2. |
| `pose report` diz "Montagem desconhecida" | O `--samples` não aponta para a pasta da B.9. Confira `$anot`. |
| `uv sync` com erro de certificado TLS | Use `--system-certs`, como está na A.1. |
| A janela OpenCV não aparece | Ela pode ter aberto atrás do terminal. Procure na barra de tarefas. |
| `Não foi possível conectar ao banco … em localhost:5432` (depois de 10 s), ou `connection refused` | A porta da URL (A.2) tem de ser a que o Docker publica: o valor de `BARNES_PG_PORT` no `.env`, ou 5433 se ele não estiver definido. Ajuste as duas URLs da A.2. |
| B.1 com dezenas de testes pulados (`Requer BARNES_TEST_DATABASE_URL`) | Defina `$env:BARNES_TEST_DATABASE_URL` e rode o `db migrate --dsn ...barnes_test` da A.2. Se o banco `barnes_test` não existir, crie com `docker exec barnes-maze-postgres-1 psql -U barnes -d barnes -c "CREATE DATABASE barnes_test"`. |
| `Erro no banco de dados` no `pose series`, `pose review` ou `catalog list` | O banco não tem a migração `0008` (US-10). Rode `uv run barnes db migrate`. |
| `Arquivo já existe` no `pose hardware` ou no `pose plan-training` (B.10) | Sobraram arquivos de um ensaio. Rode o `Remove-Item` da A.2, que apaga `data\pose\demo`. |
| A inferência simulada (B.12) diz `Intervalo util curto demais` | O trial 1 tem menos de 120 quadros no intervalo útil. Use um vídeo mais longo no `$v1`. |
| A inferência simulada diz `O contraste nao encontrou o animal` | A montagem do trial não cobre o animal ou o vídeo não tem contraste. Confira a montagem da B.3 com `uv run barnes maze show $maze`. |
| Os pontos simulados ficam longe do animal na revisão (B.13) | É limitação da simulação por contraste, não do US-10. Diga isso e marque o focinho onde o animal está. |
| `pose review` diz `Nenhum trecho pendente` logo na primeira vez | A revisão já foi salva num ensaio. Use `--todos` para rever os trechos revisados, ou refaça a demonstração desde a A.2. |
| Saiu da revisão sem querer (`Esc` ou janela fechada) | Nada foi gravado. Rode `pose review` de novo: ela reabre no primeiro trecho pendente. |
| Todas as execuções aparecem com `"reproduzivel": false` | O repositório já estava com alterações não commitadas. Faça commit antes da reunião (A.1). |
| `Move-Item` da B.14 falha porque o vídeo já está em `data\raw\movidos` | Um ensaio anterior parou no meio. Devolva o vídeo com `Move-Item data\raw\movidos\renomeado.mp4 $v1`. |
| `Move-Item` da B.15 ou da B.17 falha | Mesmo caso, com o vídeo completo: `Move-Item data\raw\movidos\completo.mp4 $vc`. |
| `pose sample` do vídeo completo acha o animal em menos de 90% dos quadros (B.9) | Faltou o `--start-frame 2038 --end-frame 6750`: sem ele, entram a mão e a caixa de partida. Apague `data\demo_anotacao\f0fd949e5eff` e rode de novo com o intervalo. |

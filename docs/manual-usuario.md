# Manual do usuário

**US-02: procedimento de calibração implementado. US-30: manual geral em rascunho.**

Manual de instalação e operação para o laboratório.

> **Critérios que este documento precisa fazer passar (US-30):**
> instalação concluída por **pessoa de fora** seguindo só este manual;
> operador processa um trial em **≤ 10 min**; funciona **offline**.
>
> Escrever pensando em quem nunca viu o projeto. Testar com alguém de fora
> **antes** do Sprint 5 — não durante.

## 1. Requisitos

| | |
|---|---|
| Sistema operacional | _D2_ |
| Python | 3.11 |
| GPU | Não obrigatória para inferência |
| Interface de calibração | Ambiente gráfico com teclado, mouse e OpenCV |
| Banco de dados | PostgreSQL — ver seção 2 |

## 2. Instalação

### 2.1 Software

Na pasta do projeto, instale as dependências com Python 3.11 e `uv`:

```bash
uv sync
uv run barnes --help
```

Os exemplos abaixo usam `barnes` com o ambiente virtual ativado. Sem ativá-lo,
substitua por `uv run barnes`. No Windows PowerShell, uma alternativa sem `uv` é:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . pytest ruff
.\.venv\Scripts\Activate.ps1
barnes --help
```

A instalação inicial exige acesso aos pacotes. Depois de instalados, a
calibração e o processamento descritos aqui funcionam sem acesso à internet,
desde que o Postgres do estudo (seção 2.2) já esteja acessível na rede local.
A janela exige `opencv-python` com suporte a interface gráfica; a variante
`opencv-python-headless` não atende esse fluxo.

### 2.2 Banco de dados

> **Ponto em aberto — US-27 RN07, resolver até o Sprint 2.**
> PostgreSQL é um **servidor**, não um arquivo: exige instalação e serviço
> rodando na máquina do laboratório. Isso atinge dois critérios de aceite de
> US-30 — instalação por pessoa de fora seguindo só o manual, e operação
> offline. Definir a via: instalador embarcado, container, ou serviço já
> existente no LNBio.
>
> Se a distribuição se mostrar inviável para o perfil do operador, **SQLite é a
> alternativa adequada** ao volume real do estudo (alguns milhões de linhas).

A calibração da US-02 usa o **mesmo** Postgres das demais tabelas do projeto
(`maze_configs`, `holes`, `trials`, ...) — não há um banco separado para a
escala. Aplique as migrações antes de calibrar (`barnes db migrate`, ver
`CLAUDE.md`). Para um servidor PostgreSQL já disponível, use uma conexão no
formato `postgresql://usuario:senha@localhost:5432/barnes`; o banco e o
usuário precisam existir, com permissão para criar as tabelas.

Cada comando aceita `--dsn` para essa conexão. Como alternativa, configure
`BARNES_DATABASE_URL` uma vez no terminal:

```powershell
$env:BARNES_DATABASE_URL = "postgresql://usuario:senha@localhost:5432/barnes"
```

A opção `--dsn` tem precedência sobre a variável de ambiente. A implantação do
servidor e a distribuição do aplicativo completo continuam pertencendo à
US-27/US-30.

## 3. Configurar uma montagem

Uma vez por arranjo de labirinto + câmera, não por trial. A geometria é
paramétrica (centro, raio, número de buracos e ângulo inicial — sem editor
de polígonos) e fica salva no banco (tabelas `maze_configs` e `holes`), não
em arquivo.

**Ainda pendente nesta seção:** rotação/referencial de sala (US-05). A escala
px→cm (US-02) já pode ser calibrada (seções 3.3 a 3.6) e fica gravada na
própria montagem (`maze_configs`, mesma linha criada em 3.1).

### 3.1 Criar uma montagem

```
uv run barnes maze create \
  --experiment-id <id> --name "<nome da montagem>" \
  --reference-frame <video ou imagem de referência> \
  --arena-diameter-cm <cm> --hole-diameter-cm <cm>
```

Por padrão abre uma janela OpenCV sobre o quadro de referência, ajustável
**com o mouse e o teclado**, sem precisar informar centro/raio/N/ângulo/alvo
na linha de comando (eles têm um valor inicial razoável e são corrigidos na
janela):

- **Tecla `a`** detecta automaticamente o centro e o raio da plataforma no
  quadro (maior região clara contígua) e já reposiciona a marca amarela de
  centro — usar antes de arrastar poupa a parte mais difícil de "achar o
  meio a olho".
- **Arraste o botão esquerdo** do centro (o detectado por `a`, ou qualquer
  ponto) até um buraco real visível — isso (re)define centro, raio **e**
  ângulo inicial de uma vez, calibrados contra um buraco de verdade (o
  ângulo vem da direção do arraste).
- **Clique com o botão direito** perto de um buraco já desenhado para
  marcá-lo como o buraco-alvo (fica vermelho).
- **`+` / `-`** aumentam/diminuem N (número de buracos) ao vivo, com teto de
  **30** (`+` não passa disso).
- **`Enter`, `q` ou `Esc`** confirma e fecha a janela, salvando a última
  geometria válida mostrada.

A marca amarela em cruz mostra onde está o centro atual, para conferir
visualmente se bate com o centro real da plataforma antes de confirmar.

As instruções também aparecem no rodapé da própria janela. Repita o arraste
quantas vezes quiser até os buracos desenhados coincidirem com os buracos
reais (Cenário 1) — cada novo arraste substitui centro/raio/ângulo
anteriores.

Se quiser informar os parâmetros manualmente em vez de usar o mouse (por
exemplo, reproduzindo uma montagem já medida), as opções `--center-x`,
`--center-y`, `--platform-radius-px`, `--hole-count`, `--start-angle-deg`,
`--target-hole-number` e `--hole-radius-px` continuam aceitas e só definem
o ponto de partida — a janela interativa ainda abre por cima. Use
`--no-interactive` para pular a janela e persistir direto os valores
informados (útil em script/teste); nesse caso `--center-x`, `--center-y` e
`--platform-radius-px` passam a ser obrigatórios.

Se algum parâmetro for inválido (N ≤ 2, raio não positivo, ou índice de
alvo fora de `0..N-1`), o comando recusa a gravação e informa qual
parâmetro falhou (com `--no-interactive`) ou simplesmente não atualiza o
desenho até um arraste válido ser feito (no modo interativo).

### 3.2 Reaproveitar uma montagem existente

```
uv run barnes maze show <id-da-montagem>
```

Lê a montagem do banco e imprime centro, raio, buracos e alvo — sem abrir
nenhuma janela. É o mesmo dado que outros comandos do pipeline vão
consultar para reaplicar a montagem a um novo trial, sem repetir a
configuração interativa.

### 3.3 A escala pertence à montagem

A escala px→cm é calibrada para a **montagem** criada na seção 3.1
(`--maze-config-id`, o mesmo id usado em `barnes maze show`). Use-a somente
com vídeos gravados na mesma posição, inclinação, zoom, enquadramento e
resolução de câmera da montagem — o programa não reconhece automaticamente
se a câmera se moveu entre gravações; essa identificação é responsabilidade
do operador.

Se a câmera mudou, crie uma **nova montagem** (`barnes maze create`) e
calibre-a separadamente; não reutilize o id de uma montagem com câmera
diferente. Vídeos com resolução diferente da referência usada na calibração
são recusados, para evitar aplicar uma escala de pixels incompatível. A
orientação da sala (rotação do referencial) permanece pendente em US-05.

### 3.4 Calibrar com dois segmentos conhecidos

1. Escolha um vídeo em que os marcadores estejam visíveis e nítidos. Os dois
   comprimentos reais devem ser conhecidos em centímetros e estar no mesmo
   plano em que a trajetória será medida.
2. Escolha segmentos em direções diferentes, de preferência próximos de
   perpendiculares. Segmentos longos e bem definidos reduzem o efeito do erro
   de clique. Não use a terceira distância de verificação nesta etapa.
3. Execute, substituindo arquivo, id da montagem e comprimentos pelos seus dados:

   ```bash
   barnes scale calibrate --video data/raw/trial.mp4 --maze-config-id 1 --length-1-cm 20 --length-2-cm 20 --frame 0
   ```

   `--frame` é o índice do quadro, começando em zero; o padrão é o primeiro
   quadro. Se omitir os comprimentos, o programa os solicita no terminal. Use
   ponto como separador decimal, por exemplo `12.5`.
4. Na janela OpenCV, clique no início e no fim do primeiro segmento, depois no
   início e no fim do segundo. São quatro pontos, na ordem 1–2 e 3–4.
5. Revise as linhas e pressione **Enter**. O sistema calcula e grava uma nova
   versão da escala no banco e informa o fator em **cm/px**.

| Controle | Ação |
|---|---|
| Clique esquerdo | Adicionar a próxima extremidade |
| Clique direito ou Backspace | Desfazer o último ponto |
| R | Apagar todos os pontos e começar novamente |
| Enter | Confirmar quando todos os pontos estiverem marcados |
| Esc, X ou fechar a janela | Cancelar sem salvar a calibração |

O programa pode reduzir a imagem exibida para caber na janela; as coordenadas
retornadas são convertidas para os pixels do quadro original. O vídeo original
não é alterado.

Para cada segmento, o cálculo é `escala = comprimento_real_cm / comprimento_px`.
O fator salvo é a média aritmética das duas escalas. Por exemplo, 20 cm sobre
200 px e 15 cm sobre 150 px produzem `0.1 cm/px`.

Antes de salvar, o sistema verifica a consistência dos dois segmentos:

- Comprimentos reais e comprimentos em pixels devem ser positivos e finitos.
- A diferença relativa entre as duas escalas, `abs(s1 - s2) / média(s1, s2)`,
  deve ser estritamente menor que **3%**. Se falhar, confira os comprimentos,
  refaça os cliques e verifique a inclinação da câmera.
- Segmentos paralelos ou quase paralelos são recusados. A separação mínima de
  1° é uma proteção geométrica da implementação para exigir duas direções;
  não é um limiar biológico do estudo.

Essa verificação de consistência é distinta da verificação independente da
RN04. Um fator escalar não corrige perspectiva nem garante a mesma exatidão em
todos os pontos da imagem. Se a cena apresentar distorção, ajuste a câmera e
repita a calibração; não compense alterando os comprimentos reais informados.

### 3.5 Verificar a exatidão com uma terceira distância

Use outra distância real conhecida que **não participou da calibração**, no
mesmo plano da trajetória. Prefira outra posição e direção da cena para avaliar
o uso da escala fora dos dois segmentos originais.

```bash
barnes scale verify --video data/raw/trial.mp4 --maze-config-id 1 --length-cm 15 --frame 0
```

Marque apenas as duas extremidades dessa terceira distância e confirme com
Enter. O comando informa o comprimento medido em centímetros e o erro:

```text
erro (%) = 100 × abs(comprimento_medido - comprimento_real) / comprimento_real
```

O resultado é aprovado somente quando **erro < 3%**. Um erro de exatamente 3%
reprova; o comando retorna código de saída 1 quando a tolerância não é atendida.
Não reutilize um dos segmentos de calibração, mesmo invertendo suas
extremidades: o sistema rejeita essa repetição. Essa proteção não substitui a
escolha de uma referência fisicamente independente pelo pesquisador.

A verificação não substitui a escala salva; ela só grava o erro medido
(`measured_error_pct`, aprovado ou não) na própria montagem, para consulta em
`barnes scale show`. Se reprovar, revise a montagem e os marcadores, calibre
novamente e repita a medição independente antes de usar as métricas no
estudo. Uma recalibração zera essa verificação — refaça-a contra a escala
nova.

### 3.6 Consultar, reaproveitar e recalibrar

Consulte a escala atual da montagem:

```bash
barnes scale show --maze-config-id 1
```

Para processar outro vídeo com a mesma montagem, use o mesmo
`--maze-config-id`. A escala atual é aplicada automaticamente, sem marcar
novos pontos.

Para corrigir a calibração, execute novamente `barnes scale calibrate` com o
mesmo `--maze-config-id`. A operação **sobrescreve** a escala da montagem
(RN05) — não existe histórico de versões anteriores. Os resultados já
calculados (`barnes metrics process`) para trials dessa montagem ficam
**obsoletos**: o valor calculado com a escala anterior continua no banco,
mas `barnes metrics executions` passa a marcá-lo como tal.

Reprocesse os trials afetados para atualizar o resultado com a escala atual.
O sistema não recalcula nem apaga resultados antigos silenciosamente. Para
examinar o estado de um trial:

```bash
barnes metrics executions --trial 1
```

Esse comando apresenta o resultado, as métricas e se ficou obsoleto. Ao
comparar resultados entre trials, considere somente os que não estão
obsoletos. Se a câmera mudou fisicamente, crie uma **nova montagem**
(`barnes maze create`) em vez de recalibrar a mesma: os vídeos antigos ainda
pertencem à montagem em que foram gravados.

## 4. Processar um trial

### 4.1 Processamento de métricas disponível na US-02

O processamento desta entrega recebe uma trajetória já extraída, em CSV. A
extração automática da trajetória a partir do vídeo pertence às outras
histórias do projeto e ainda precisa ser integrada. O CSV deve conter as
colunas `x_px`, `y_px` e `time_s`, com ao menos duas amostras, números finitos e
tempos não negativos e estritamente crescentes, em segundos. As coordenadas
devem ficar dentro do quadro e usar os pixels do vídeo original. Amostras
ausentes precisam ser tratadas antes de fornecer a trajetória.

Exemplo de `data/interim/trial.csv`:

```csv
x_px,y_px,time_s
10,20,0
40,60,1
70,100,2
```

```bash
barnes metrics process --video data/raw/trial.mp4 --trajectory data/interim/trial.csv --trial 1 --maze-config-id 1
```

`--trial` é o id do trial já carregado no banco (`barnes video load`); `--frame`
(padrão 0) escolhe o quadro usado para confirmar a resolução, igual a `scale
calibrate`/`scale verify`. O programa exige uma escala válida para a
montagem, verifica se a resolução do vídeo bate com a da calibração, e
calcula a distância percorrida em centímetros e a velocidade média em cm/s.
Sem escala, o cálculo é bloqueado — antes mesmo de abrir o vídeo — com uma
mensagem solicitando a calibração daquela montagem. O resultado salvo
registra a escala exata usada (`px_per_10cm_used`), para detectar se fica
obsoleto numa recalibração futura.

A distância é a soma dos deslocamentos entre amostras. A velocidade média é
essa distância dividida pelo tempo entre a primeira e a última amostra. No CSV
acima, uma escala de `0.1 cm/px` resulta em 10 cm percorridos em 2 s, ou 5 cm/s.
Essas métricas não acrescentam interpolação, suavização ou detecção de eventos.

Opcionalmente, informe `--ideal-distance-px` com a distância ideal da rota,
medida no mesmo referencial de pixels. A eficiência é a razão entre a distância
ideal e a distância percorrida; embora seja adimensional, também exige escala
calibrada conforme a RN03. A distância ideal não pode exceder a percorrida. Se
ambas forem zero, a eficiência é indefinida e aparece como `null` no resultado.
A determinação automática dessa rota pertence à geometria e às demais
histórias do projeto.

### 4.2 Fluxo completo de vídeo

_A preencher nas demais histórias. O procedimento completo cronometrado do
critério de ≤ 10 min da US-30 ainda precisa de validação com um operador._

### 4.1 Recorte do intervalo útil (US-03)

Ao carregar um trial com `barnes video load`, o sistema sempre resolve um
**intervalo útil** — o trecho do vídeo entre a soltura do animal e o fim do
trial — antes de persistir. Nenhuma métrica, evento ou ponto de trajetória
calculado por estágios posteriores do pipeline usa quadros fora desse
intervalo (RN02); e o tempo zero de qualquer latência reportada é o início
do intervalo, não o início do arquivo de vídeo (RN05).

```
uv run barnes video load <video.mp4> \
  --experiment-id <id> --maze-config-id <id> \
  [--start-s <segundos> | --start-frame <quadro>] \
  [--end-s <segundos> | --end-frame <quadro>]
```

- **Sem nenhuma das opções acima** (fluxo principal, Cenário 1): o início é
  proposto automaticamente por uma heurística de movimento — compara cada
  quadro ao anterior e procura o primeiro trecho de movimento sustentado
  (remoção do cilindro ou o próprio animal se movendo), distinguindo isso
  do "parado" dos quadros iniciais. O fim é o fim do vídeo, já que este
  card não detecta automaticamente o momento da fuga (isso depende dos
  eventos por buraco de um card posterior). O intervalo proposto aparece
  no terminal antes de ser salvo — rodar o comando sem flags **é** a
  confirmação do valor proposto.
- **Com `--start-s`/`--start-frame` e/ou `--end-s`/`--end-frame`** (fluxo
  alternativo, Cenário 2): os valores informados substituem a proposta
  automática. O trial fica marcado como **"ajustado manualmente"**
  (coluna `interval_manually_adjusted`) — use quando a detecção automática
  errar o instante de soltura. Informe cada limite em segundos **ou** em
  número de quadro, nunca os dois para o mesmo limite.
- O comando recusa o recorte (sem salvar nada) se o fim não for maior que
  o início, ou se algum dos dois cair fora da duração do vídeo.

O intervalo efetivamente usado — início, fim e se foi ajuste manual — fica
gravado no registro do trial (`trials.start_time_seconds`,
`trials.end_time_seconds`, `trials.interval_manually_adjusted`) e pode ser
conferido depois, para auditoria (RN04).

> **Pendente:** a tarefa "validar a heurística nos 3 trials representativos
> de G1" depende de G1 ter acontecido (receber vídeos reais do LNBio — ver
> seção 2 da definição do projeto). A heurística acima é um ponto de
> partida genérico, calibrado só contra vídeo sintético; revisitar o limiar
> de movimento (`_MOTION_THRESHOLD_STD` em `src/barnes/io/trim.py`) assim
> que houver trials reais.

## 5. Saídas

Na US-02, os resultados são exibidos no terminal e persistidos no mesmo
Postgres do projeto. Use `barnes scale show` e `barnes metrics executions`
para consultar os registros.
As exportações do produto completo abaixo permanecem previstas para suas
respectivas histórias:

| Arquivo | Conteúdo |
|---|---|
| CSV por trial | métricas do trial |
| CSV consolidado | todos os trials |
| `trials.csv` / `probes.csv` | formato que o `barnes_maze.py` do laboratório lê sem alteração (US-25) |
| Curvas e trajetória desenhada | |

## 6. Problemas comuns

| Situação | Procedimento |
|---|---|
| Montagem sem escala | Execute `barnes scale calibrate` com o mesmo `--maze-config-id` do processamento. |
| Escalas dos segmentos divergem | Confira unidades, cliques, plano dos marcadores e perspectiva; repita a calibração. |
| Segmentos têm a mesma direção | Escolha uma segunda referência em outra direção, preferencialmente perpendicular. |
| Erro independente ≥ 3% | Revise a montagem e calibre novamente antes de usar as métricas. |
| Resolução diferente da referência | Use os vídeos originais dessa montagem, ou crie outra montagem (`maze create`) e calibre-a. |
| Janela não abre | Execute em sessão gráfica com `opencv-python` e acesso ao monitor; a interface interativa exige janela. |
| Vídeo/quadro não pode ser lido | Confira caminho, formato e índice do quadro; o primeiro quadro é o 0. |
| Resultado parece ausente | Confira `--dsn`/`BARNES_DATABASE_URL` e o id do trial/da montagem. |
| Resultado marcado obsoleto | Reprocesse o trial (`metrics process`) para aplicar a escala atual; o valor anterior fica até reprocessar. |

_Outros problemas serão acrescentados nas demais histórias, especialmente o
aviso de fps variável (US-01), que não é corrigido automaticamente._

## 7. API e verificação para desenvolvimento

### 7.1 Calibração sem janela

A coleta de cliques (`barnes.io.calibration_ui`), o cálculo
(`barnes.io.calibration`) e a persistência (`barnes.db.calibration`) são
módulos independentes. Um programa pode fornecer os pontos diretamente, sem
importar ou abrir a interface OpenCV:

```python
from barnes.db.calibration import save_calibration, require_calibration
from barnes.db.connection import get_connection
from barnes.io.calibration import Segment, calculate_calibration, verify_distance

result = calculate_calibration(
    [
        Segment((10, 10), (210, 10), 20),
        Segment((10, 30), (10, 230), 20),
    ]
)
print(result.cm_per_px)  # 0.1

with get_connection() as conn:  # usa BARNES_DATABASE_URL se omitido
    save_calibration(
        conn,
        maze_config_id=1,
        result=result,
        reference_video="data/raw/trial.mp4",
        reference_frame=0,
        reference_size=(640, 480),  # largura, altura do quadro original
    )
    calibration = require_calibration(conn, 1)

check = verify_distance(result, Segment((300, 100), (450, 100), 15))
print(check.accepted, check.relative_error)  # True, 0.0
```

Esse exemplo sobrescreve a escala da montagem (RN05) e tem os mesmos efeitos
de recalibração do CLI; use um `maze_config_id` e banco de testes ao
experimentar. `collect_segments(frame)`, em `barnes.io.calibration_ui`, cuida
exclusivamente da seleção interativa e retorna pares de pontos no
referencial original — não calcula nem persiste nada.

### 7.2 Testes

```bash
python -m pytest
python -m ruff check .
```

Os testes incluem imagem sintética com escala conhecida e uma terceira
distância independente, bloqueio sem escala, reutilização pela montagem e
obsolescência após recalibração. Os testes da janela simulam os eventos do
OpenCV; não substituem uma sessão manual com vídeo real. Os testes de
persistência (`tests/db/`, `tests/test_cli.py`) exigem `BARNES_DATABASE_URL`
apontando para um Postgres de teste com o schema aplicado (`barnes db
migrate`) — são pulados automaticamente se a variável não estiver definida.

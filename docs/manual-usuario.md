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
| Banco de dados | SQLite local ou PostgreSQL — ver seção 2 |

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
calibração e o processamento descritos aqui funcionam com arquivos locais e
SQLite, sem acesso à internet. A janela exige `opencv-python` com suporte a
interface gráfica; a variante `opencv-python-headless` não atende esse fluxo.

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

Para a US-02, o padrão é o arquivo local `data/barnes.sqlite3`. As tabelas são
criadas automaticamente ao usar os comandos; não é necessário instalar um
servidor para experimentar a calibração. Guarde uma cópia desse arquivo junto
ao estudo, pois contém as escalas, suas versões e o histórico das execuções.

Cada comando aceita `--database` para selecionar outro arquivo ou uma conexão
PostgreSQL. Como alternativa, configure `BARNES_DATABASE` uma vez no terminal:

```powershell
$env:BARNES_DATABASE = "data/estudo-01.sqlite3"
```

Para um servidor PostgreSQL já disponível, use uma conexão no formato
`postgresql://usuario:senha@localhost:5432/barnes`. O banco e o usuário precisam
existir, com permissão para criar as tabelas. A implantação do servidor e a
distribuição do aplicativo completo continuam pertencendo à US-27/US-30.

Use sempre o mesmo banco nos comandos do estudo. A opção `--database` tem
precedência sobre a variável de ambiente. Trocar de banco não transfere as
calibrações anteriores.

## 3. Configurar uma montagem

### 3.1 Identificar a orientação da câmera

A escala pertence a uma **orientação de câmera**, identificada por um nome
fornecido em `--orientation`, por exemplo `camera-dia-01`. Reutilize esse nome
somente em vídeos com a mesma posição, inclinação, zoom, enquadramento e
resolução. A identificação é responsabilidade do operador: o programa não
reconhece automaticamente se a câmera se moveu entre gravações.

Se a câmera mudou, crie outro identificador e calibre essa nova orientação.
Mesmo no mesmo estudo, orientações diferentes mantêm escalas independentes.
Vídeos com resolução diferente da referência são recusados para evitar aplicar
uma escala de pixels incompatível. O procedimento completo de configuração de
plataforma, buracos e orientação da sala permanece pendente em US-04/US-05.

### 3.2 Calibrar com dois segmentos conhecidos

1. Escolha um vídeo em que os marcadores estejam visíveis e nítidos. Os dois
   comprimentos reais devem ser conhecidos em centímetros e estar no mesmo
   plano em que a trajetória será medida.
2. Escolha segmentos em direções diferentes, de preferência próximos de
   perpendiculares. Segmentos longos e bem definidos reduzem o efeito do erro
   de clique. Não use a terceira distância de verificação nesta etapa.
3. Execute, substituindo arquivo, orientação e comprimentos pelos seus dados:

   ```bash
   barnes calibrate --video data/raw/trial.mp4 --orientation camera-dia-01 --length-1-cm 20 --length-2-cm 20 --frame 0
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

### 3.3 Verificar a exatidão com uma terceira distância

Use outra distância real conhecida que **não participou da calibração**, no
mesmo plano da trajetória. Prefira outra posição e direção da cena para avaliar
o uso da escala fora dos dois segmentos originais.

```bash
barnes verify-scale --video data/raw/trial.mp4 --orientation camera-dia-01 --length-cm 15 --frame 0
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

A verificação não substitui a escala salva. Se reprovar, revise a montagem e
os marcadores, calibre novamente e repita a medição independente antes de usar
as métricas no estudo.

### 3.4 Consultar, reaproveitar e recalibrar

Consulte a escala atual ou todas as versões da orientação:

```bash
barnes scale --orientation camera-dia-01
barnes scale --orientation camera-dia-01 --history
```

Para processar outro vídeo com a mesma orientação, use o mesmo identificador
e banco. A escala atual é aplicada automaticamente, sem marcar novos pontos.

Para corrigir a calibração da **mesma orientação**, execute novamente
`barnes calibrate` com aquele identificador. A operação cria uma versão nova;
as versões anteriores permanecem no banco. As métricas das execuções anteriores
daquela orientação ficam **inválidas**, mas cada execução mantém o identificador
da escala que usou e seus valores originais para auditoria. Execuções de outras
orientações continuam válidas.

Reprocesse os trials afetados para gerar novas execuções usando a escala atual.
O sistema não recalcula nem apaga as execuções antigas silenciosamente. Para
examinar esse histórico:

```bash
barnes executions --trial trial-01
```

Esse comando apresenta as execuções, a escala utilizada, as métricas e sua
validade. Ao comparar resultados, considere somente execuções válidas. Se a
câmera mudou fisicamente, use uma **nova orientação** em vez de recalibrar a
anterior: os vídeos antigos ainda pertencem à montagem em que foram gravados.

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
barnes process --video data/raw/trial.mp4 --trajectory data/interim/trial.csv --trial trial-01 --orientation camera-dia-01
```

O programa exige uma escala válida para a orientação, verifica a resolução do
vídeo e calcula a distância percorrida em centímetros e a velocidade média em
cm/s. Sem escala, a execução é bloqueada com uma mensagem solicitando a
calibração daquela orientação. Cada execução salva referencia a versão exata
da escala aplicada.

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

## 5. Saídas

Na US-02, os resultados são exibidos no terminal e persistidos no banco
selecionado. Use `barnes scale` e `barnes executions` para consultar os registros.
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
| Orientação sem escala | Execute `barnes calibrate` com o mesmo identificador e banco do processamento. |
| Escalas dos segmentos divergem | Confira unidades, cliques, plano dos marcadores e perspectiva; repita a calibração. |
| Segmentos têm a mesma direção | Escolha uma segunda referência em outra direção, preferencialmente perpendicular. |
| Erro independente ≥ 3% | Revise a montagem e calibre novamente antes de usar as métricas. |
| Resolução diferente da referência | Use os vídeos originais da orientação correta ou crie outra orientação e calibre. |
| Janela não abre | Execute em sessão gráfica com `opencv-python` e acesso ao monitor; a interface interativa exige janela. |
| Vídeo/quadro não pode ser lido | Confira caminho, formato e índice do quadro; o primeiro quadro é o 0. |
| Histórico parece vazio | Confira `--database`, `BARNES_DATABASE`, nome do trial e da orientação. |
| Execução marcada inválida | Reprocesse o trial para aplicar a versão atual; mantenha a execução antiga para auditoria. |

_Outros problemas serão acrescentados nas demais histórias, especialmente o
aviso de fps variável (US-01), que não é corrigido automaticamente._

## 7. API e verificação para desenvolvimento

### 7.1 Calibração sem janela

A coleta de cliques é separada do cálculo e da persistência. Um programa pode
fornecer os pontos diretamente, sem importar ou abrir a interface OpenCV:

```python
from barnes.db import CalibrationRepository
from barnes.io.calibration import Segment, calibrate_orientation, verify_distance

with CalibrationRepository("data/barnes.sqlite3") as repository:
    calibration = calibrate_orientation(
        repository,
        "camera-dia-01",
        [
            Segment((10, 10), (210, 10), 20),
            Segment((10, 30), (10, 230), 20),
        ],
        reference_video="data/raw/trial.mp4",
        reference_frame=0,
        reference_size=(640, 480),  # largura, altura do quadro original
    )

print(calibration.result.cm_per_px)  # 0.1
check = verify_distance(
    calibration.result,
    Segment((300, 100), (450, 100), 15),
)
print(check.accepted, check.relative_error)  # True, 0.0
```

Esse exemplo grava uma versão e tem os mesmos efeitos de recalibração do CLI;
execute com um identificador e banco de testes ao experimentar. Para apenas
calcular em memória, use `calculate_calibration(segments)`, do mesmo módulo.
`collect_segments(frame)`, em `barnes.io.calibration_ui`, cuida exclusivamente
da seleção interativa e retorna pares de pontos no referencial original.

### 7.2 Testes

```bash
python -m pytest
python -m ruff check .
```

Os testes incluem imagem sintética com escala conhecida e uma terceira
distância independente, bloqueio sem escala, reutilização por orientação e
histórico após recalibração. Os testes da janela simulam os eventos do OpenCV;
não substituem uma sessão manual com vídeo real. Os testes opcionais de
PostgreSQL usam `BARNES_TEST_POSTGRES_DSN` apontando para um banco de testes.

# barnes-maze

Quantificação do aprendizado espacial no labirinto de Barnes — extração
automática de trajetória, eventos por buraco e estratégia de busca a partir de
vídeo zenital de trial.

**Cliente:** LNBio · **Prazo:** 10 semanas, 5 sprints · **Equipe:** 5 integrantes

O software entrega os **dados**; a análise estatística de sobrevivência
permanece com o cliente, no `barnes_maze.py` que ele já domina. A ponte entre as
duas coisas é a exportação compatível com `trials.csv` e `probes.csv` (US-25).

A definição de escopo completa — cards, riscos, cronograma e critérios de aceite
— está em `definicao-projeto.md`, no diretório acima deste repositório.

## O que este projeto entrega

O que só ele pode entregar, e que a anotação manual não consegue produzir:

- **Eventos por buraco** — separar *encontrar* de *entrar*, com dwell e ordem de visitação
- **Orientação da cabeça** — para onde o animal olhava, não só por onde passou
- **Sequência completa de visitação** e classificação de estratégia
- **Exportação compatível** com o pipeline estatístico do laboratório

## Estrutura

```
barnes-maze/
├── configs/
│   ├── default.yaml              # limiares operacionais — valores vêm de G3
│   ├── pose/single_animal.yaml   # perfil inicial de treino SLEAP-NN
│   └── montagens/README.md       # geometria persistida no PostgreSQL
├── src/barnes/
│   ├── io/                       # vídeo, escala px→cm, fps, recorte do trial
│   ├── pose/                     # inferência SLEAP, série x, y, θ, t
│   ├── geometry/                 # plataforma, buracos, rotação, referencial da sala
│   ├── events/                   # encontrar, entrar, dwell, ordem de visitação
│   ├── metrics/                  # latência, erros, distância, eficiência, entropia
│   ├── strategy/                 # classificador por regra e validação
│   ├── longitudinal/             # curvas, DTW/Fréchet, probe, palpites
│   ├── stats/                    # qui-quadrado / Fisher sobre estratégias, kappa
│   ├── report/                   # CSV, PDF, gráficos
│   ├── db/                       # esquema PostgreSQL e acesso
│   └── cli.py
├── data/                         # NÃO versionado
│   ├── raw/                      # vídeos originais — somente leitura
│   ├── annotations/              # rótulos de pose
│   ├── interim/                  # trajetórias .parquet
│   └── processed/                # métricas e relatórios
├── models/                       # NÃO versionado — pesos do modelo de pose
├── notebooks/
├── tests/
│   └── fixtures/                 # trial de referência + resultado esperado
└── docs/
    ├── definicoes-metricas.md    # ← marco M1, aceite do cliente
    ├── protocolo-anotacao.md
    └── manual-usuario.md
```

### Quatro regras que fazem a estrutura valer alguma coisa

1. **`data/` e `models/` ficam fora do Git**, e `data/raw/` é somente leitura.
   Como estão no `.gitignore`, quem clona o repositório precisa **recriar essas
   pastas** — ver *Setup* abaixo.
2. **`notebooks/` é rascunho.** Nada que exista só ali conta como entregue.
3. **`configs/montagens/` é registro** de qual geometria produziu quais números.
   Versionado, sempre.
4. **`stats/` é separado de `longitudinal/`** porque os testes vão mudar depois
   da conversa com o estatístico.

E uma quinta, que vale por todas: **geometria e limiares são configuração, não
código.** Quando o laboratório revisar a definição de "encontrar" — e vai
revisar —, muda-se um número em `configs/` e reprocessa, sem tocar em visão
computacional.

## Setup

Requer [uv](https://docs.astral.sh/uv/) e Python 3.11.

```bash
uv sync
mkdir -p data/raw data/annotations data/interim data/processed models
```

O `uv.lock` é gerado por `uv lock` e **deve ser versionado**: é ele que garante
que o modelo treinado na semana 4 ainda roda na semana 12.

Extras opcionais:

```bash
uv sync --extra pose          # SLEAP — ler o aviso no pyproject.toml antes
uv sync --extra anotacao      # leitor do .slp do SLEAP (sleap-io), sem CUDA (US-06)
uv sync --extra longitudinal  # DTW / Fréchet (US-24)
```

## Uso

Carregar um vídeo de trial e ver os metadados (US-01):

```bash
uv run barnes video load "data/OF_Animal_22_240919.mp4"
```

Mostra resolução, fps real medido (não o do cabeçalho do contêiner), duração,
número de quadros e o hash do arquivo, e abre uma janela navegável entre
quadros (`n`/`d` = próximo, `p`/`a` = anterior, `q`/Esc = fechar) — útil
porque o primeiro quadro pode estar obstruído.

Para também persistir o trial em `trials` (exige um `experiment` e um
`maze_config` já cadastrados):

```bash
uv run barnes video load "data/OF_Animal_22_240919.mp4" \
    --experiment-id 1 --maze-config-id 1 \
    --phase acquisition --day 1 --trial-in-day 1
```

Use `--no-preview` para rodar sem abrir janela (scripts, CI).

## Banco de dados

O schema (Postgres puro, sem ORM) mora em `database/migrations/`, gerado a
partir de `docs/DER.md`.

Para desenvolvimento local, suba um Postgres descartável com Docker Compose:

```bash
cp .env.example .env      # uma vez — o .env não é commitado
docker compose up -d      # Postgres na porta 5433 (não colide com um nativo na 5432)
uv run barnes db migrate
uv run barnes db migrate --dsn postgresql://barnes:barnes@localhost:5433/barnes_test
```

(Contra o Postgres real do laboratório, troque só o `BARNES_DATABASE_URL` no
`.env`.) O banco `barnes_test` é só da suíte de testes
(`BARNES_TEST_DATABASE_URL`); os testes nunca tocam o banco de trabalho. Numa
próxima sessão: abra o Docker Desktop e rode `docker compose up -d`. A
máquina do laboratório usa PostgreSQL instalado nativamente (decisão da
SCRUM-148) — passo a passo em `docs/manual-usuario.md` §2.2.2.

Migrações são arquivos `.sql` numerados (`0001_...`, `0002_...`), aplicados em
ordem e registrados em `schema_migrations` — rodar o comando de novo não
reaplica o que já foi feito. Alterações de schema viram um novo arquivo
`NNNN_descricao.sql`, nunca uma edição do anterior.

O acesso ao banco em `src/barnes/db/` usa `psycopg` diretamente (sem ORM):
schema explícito em SQL, consistente com a regra de que geometria e limiares
são configuração, não abstração escondida em código.

## Calibração px → cm (US-02)

A calibração usa dois segmentos conhecidos, marcados em uma janela OpenCV, e
salva a escala direto na montagem (`maze_configs`, no mesmo Postgres do
resto do projeto — sem banco separado). Use `--maze-config-id` com o id de
uma montagem já criada por `barnes maze create`.

```bash
uv run barnes scale calibrate --video data/raw/trial.mp4 --maze-config-id 1 --length-1-cm 20 --length-2-cm 20
uv run barnes scale verify --video data/raw/trial.mp4 --maze-config-id 1 --length-cm 15
uv run barnes scale show --maze-config-id 1
```

Clique nas quatro extremidades em ordem, dois pontos por segmento, e confirme
com Enter. Para verificar a exatidão, marque uma terceira distância independente;
o erro aceito é estritamente menor que 3%. Uma recalibração sobrescreve a
escala da montagem (RN05) e invalida os resultados calculados com a escala
anterior — eles ficam no banco, mas marcados como obsoletos até reprocessar.

O processamento disponível recebe uma trajetória existente em CSV com as
colunas `x_px,y_px,time_s` (`time_s` desde o início do vídeo). A montagem e o
intervalo útil (US-03) vêm do próprio trial, e só as amostras dentro do
intervalo entram nas métricas. A inferência automática de trajetória a partir
do vídeo permanece nas demais histórias do projeto.

```bash
uv run barnes metrics process --video data/raw/trial.mp4 --trajectory data/interim/trial.csv --trial 1
uv run barnes metrics executions --trial 1 [--history]
```

## Proveniência e catálogo (US-27)

Cada `metrics process` grava uma linha em `execucao` com limiares
(`configs/default.yaml`), parâmetros, commit e se havia alterações não
commitadas, e as métricas apontam para ela — métrica sem execução é recusada
pelo próprio banco. O vídeo é conferido pelo hash antes do cálculo.

```bash
uv run barnes execution show 42          # tudo o que a execução 42 usou
uv run barnes catalog list               # trial, animal, sessão, situação, cobertura, arquivo
uv run barnes catalog list --verificar-hash --procurar-em D:/videos   # vídeos movidos/alterados
```

Sem escala para a montagem, o cálculo é bloqueado. O procedimento completo,
os controles da janela, a API sem interface gráfica e a recalibração estão no
[manual do usuário](docs/manual-usuario.md).

## Anotação de pose (US-06)

Prepara o conjunto de treino do modelo de pose: escolhe quadros com o animal
no centro, na borda e perto dos buracos, converte as anotações feitas no
SLEAP, divide em treino/validação/teste **por trial** e verifica que nenhum
trial vazou entre conjuntos.

```bash
uv run barnes pose sample --video data/raw/trial.mp4 --maze-config-id 1   # exporta PNGs
# ... anotar no SLEAP (focinho, centro_corpo, base_cauda) ...
uv run barnes pose import-slp data/annotations/projeto.slp
uv run barnes pose split
uv run barnes pose check-split
uv run barnes pose report   # montagem de cada trial, registrada pelo sample
```

Parâmetros do protocolo na seção `anotacao` de `configs/default.yaml`; passo a
passo completo em [docs/protocolo-anotacao.md](docs/protocolo-anotacao.md).

Para verificar a implementação:

```bash
uv run python -m pytest
uv run python -m ruff check .
```

## Treino, avaliação e inferência de pose (US-07/US-08)

SLEAP-NN 0.3.1 / PyTorch, versões fixadas em `pyproject.toml` e `uv.lock`.
O fluxo prepara pacotes de quadros rotulados por montagem, treina e versiona
pesos em `models/`, avalia erro global e por região e executa inferência local
por trial. Hiperparâmetros, dados, ambiente, máquina e tempos ficam nos
manifestos e na tabela `execucao` (migração `0006`).

```powershell
uv run --no-sync barnes pose hardware --out data/pose/hardware.json
uv run --no-sync barnes pose prepare-training --maze-config-id 1
uv run --no-sync barnes pose train --dataset data/pose/datasets/dataset-<id>
uv run --no-sync barnes pose evaluate --model models/<id> --dataset data/pose/datasets/dataset-<id>
uv run --no-sync barnes pose infer --model models/<id> --trial 1
```

Instalação CUDA, fallback/D4, parâmetros, recuperação e aceite offline estão
em [Treino e avaliação de pose](docs/pose-treino-avaliacao.md). Os caminhos
`<id>` são preenchidos com as saídas reais dos comandos. Treino requer dados
anotados e NVIDIA elegível; a implementação não inclui pesos treinados do
laboratório.

A pose bruta (`pose.csv`, em pixels) vira a **série de trajetória** da US-09 —
uma linha por quadro do intervalo útil, posição em cm, orientação da cabeça θ em
graus e t desde a soltura —, gravada em `data/interim/trial_<id>.parquet` sob o
contrato de [`docs/contrato-trajetoria.md`](docs/contrato-trajetoria.md):

```powershell
uv run barnes pose series --trial 1 --inference data/pose/inference/inferencia-<id>
```

## Antes de escrever código

Dois avisos que valem mais que qualquer linha deste repositório:

**Não preencha os limiares de `configs/default.yaml` por conta própria.** Eles
estão em `null` de propósito. Distância e ângulo de "encontrar", dwell, critério
de erro, limiares de estratégia — todos vêm do laboratório via portão G3 e são
calibrados contra anotação manual. Valores escolhidos por conveniência produzem
números plausíveis e bem formatados, sem relação com o que o laboratório chama
de latência. Ver `docs/definicoes-metricas.md`.

**Confira a licença de todo pacote antes de adotar.** US-30 exige nenhuma
dependência GPL/AGPL na distribuição. Por isso `scipy` + `scikit-learn` em vez
de `pingouin` (GPL-3), e por isso adotar YOLO-pose (AGPL) seria decisão do
cliente, não da equipe. Com desenvolvimento assistido por IA, a chance de uma
sugestão GPL entrar sem revisão aumenta.

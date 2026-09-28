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
│   └── montagens/
│       └── lnbio_barnes.yaml     # geometria por arranjo labirinto + câmera
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
docker compose up -d
export BARNES_DATABASE_URL="postgresql://barnes:barnes@localhost:5432/barnes"
uv run barnes db migrate
```

(Contra o Postgres real do laboratório, troque só o `BARNES_DATABASE_URL`.)

Migrações são arquivos `.sql` numerados (`0001_...`, `0002_...`), aplicados em
ordem e registrados em `schema_migrations` — rodar o comando de novo não
reaplica o que já foi feito. Alterações de schema viram um novo arquivo
`NNNN_descricao.sql`, nunca uma edição do anterior.

O acesso ao banco em `src/barnes/db/` usa `psycopg` diretamente (sem ORM):
schema explícito em SQL, consistente com a regra de que geometria e limiares
são configuração, não abstração escondida em código.

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

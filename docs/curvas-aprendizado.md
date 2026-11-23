# Curvas de aprendizado por sessão — US-22

Implementação na branch `US-22/Tales`, criada de `origin/main` (`46a05b5`).

## Uso

```powershell
uv sync --locked
uv run barnes db migrate
uv run barnes metrics learning-curves --experiment 1 --experiment 2
uv run barnes metrics learning-curves --phase acquisition --event primary --out data/reports/learning
```

Use os IDs reais. O filtro `--experiment` pode ser repetido para selecionar o
grupo; sem filtro, todos os animais da fase são incluídos. No esquema atual,
cada experimento possui um animal. Sessão é `trials.day_number`, coerente com
a VIEW `sessao`. Fases não são misturadas: o padrão é `acquisition`; também
são aceitas `habituation` e `probe`. `--dsn` substitui `BARNES_DATABASE_URL`.

Cada chamada cria um diretório UUID com uma figura de quatro painéis por animal
e outra para o grupo, em **PNG (160 dpi), PDF e SVG**, além de `manifest.json`.
PNG pode ser incorporado diretamente ao notebook/documento executável do
laboratório; PDF e SVG preservam os vetores. Não há dependência de tela/GUI.
Saídas antigas não são sobrescritas; falhas removem somente a tentativa nova.

## Métricas e agregação

| Painel | Banco | Unidade |
|---|---|---|
| Latência | `primary_latency_s` (padrão) ou `total_latency_s` | segundos desde S |
| Erros | `primary_errors` (padrão) ou `total_errors` | contagem |
| Distância | `distance_cm` | cm percorridos no trial |
| Entropia | `entropy_bits` | bits (logaritmo base 2) |

`--event primary` seleciona descoberta do alvo; `--event total`, entrada no
alvo. Erros totais se referem ao trial inteiro. Distância é o deslocamento do
trial (US-18), não a distância até D/E. Entropia deve chegar já calculada pelo
estágio responsável; o gerador de curvas não calcula métricas a partir de pose.

Por animal/sessão, usa-se a média dos trials bem-sucedidos com valor disponível
e escala vigente. Para o grupo, calcula-se a média dessas médias e o **desvio
padrão amostral entre animais**. Cada animal tem peso igual mesmo com números
de trials diferentes. `n` é impresso na curva; com um animal não há estimativa
de dispersão (DP `null`), nem barra fictícia zero. Sessões sem valores válidos
produzem lacunas, não zeros. As curvas são descritivas e condicionadas ao
sucesso; não estimam latência populacional nem substituem análise de sobrevivência.

## Censura, ausências e qualidade

- `primary_event`/`total_event`: `true` = observado, `false` = censurado,
  `null` = não avaliado. São independentes, seguindo a US-16.
- Censurados aparecem como triângulos abertos e são contados por sessão no
  rodapé, inclusive quando não possuem valor numérico. Não entram nas médias.
- Estado de censura desconhecido aparece como cruz cinza quando há valor,
  também fora da média. Dados ausentes nunca viram zero/sucesso/censura.
- Resultados obsoletos após recalibração são contados e excluídos do traçado.
  Registros sem escala/data de cálculo verificável também não entram nas médias.
- A qualidade atual da pose aparece no rodapé e por trial no manifesto; não
  constitui uma nova avaliação de pose feita pelo relatório.

## Proveniência e integração com os próximos cards

A consulta usa exclusivamente PostgreSQL e seleciona uma linha de
`trial_results` por trial: maior `calculated_at`, com `id` como desempate.
Não combina colunas de execuções diferentes. Se o último processamento tiver
apenas distância, as demais métricas ficam ausentes, mesmo se uma execução
antiga as tiver. O manifesto preserva todos os valores consultados, IDs,
modelo, commit/estado sujo, limiares completos/hash e parâmetros de origem.
Cada figura imprime todas as execuções pertinentes, modelo, commit completo
e SHA-256 dos limiares; metadados desconhecidos são identificados.

A migração **0011** acrescenta `primary_event`, `total_event` e `entropy_bits`
como campos opcionais. O campo legado `event_ocurred` não é convertido, pois
não especifica inequivocamente descoberta ou entrada. `insert_trial_result`
agora aceita esses campos, latências e erros: o estágio produtor deve gravá-los
com a mesma execução e transação das métricas. Ao converter `CensoredMeasure.event`
da US-16, preservar `None` e converter 0/1 em bool explicitamente.

**Pendência de integração dos produtores:** a `main` de origem ainda não possui
cálculo/persistência de entropia, e os comandos existentes não persistem juntos
latências, erros e os estados explícitos de censura. Este card fornece a leitura,
o contrato de gravação e as figuras; não inventa resultados para completar
painéis. As US-16/17/20 e a integração do processamento devem preencher o
contrato para obter curvas completas com dados reais. A entropia é da US-20
(US-19 é eficiência de rota). A equipe já adotou limiares provisórios em
12/11/2026, conforme `decisoes-sem-laboratorio.md`; a US-22 não os altera nem
atribui a eles aceite do laboratório. D3/G3 continuam pendentes.

## Verificação e cobertura

Os testes usam vários animais, sessões, execuções e censura. Conferem médias
com pesos iguais, DP, valores ausentes, versão mais recente, filtros, escala
obsoleta, proveniência, exportação e limpeza em caso de falha. O teste de CLI
recusa qualquer abertura de vídeo, Parquet, SLP ou `data/raw/`; o teste PostgreSQL
usa caminhos de vídeos inexistentes e gera as figuras diretamente da consulta.

```powershell
# Configurar BARNES_TEST_DATABASE_URL somente para banco descartável migrado.
uv run --no-sync python -m pytest tests/longitudinal/test_learning.py tests/db/test_learning.py
```

SCRUM-257–263 estão cobertos por consulta, curva individual, agregação/DP,
censura, proveniência, teste sem mídia e exportação, respectivamente. A validação
com a base real do laboratório depende de métricas persistidas nessa base.

### Resultado da verificação — 23/11/2026

- Suíte completa com PostgreSQL local de teste: **1212 aprovados, 3 pulados,
  nenhuma falha**. Os pulados são dois testes opcionais SLEAP-NN e um AF_UNIX
  indisponível no Windows; nenhum teste de banco foi pulado.
- Verificação final dos arquivos alterados, incluindo a nova regressão US-22
  do trial de referência acrescentada durante a revisão: **32 aprovados**.
- Ruff e `git diff --check` passaram; figuras com dados sintéticos foram
  inspecionadas visualmente após corrigir a disposição do título e rodapé.
- Migrações aplicadas somente ao banco descartável, sem modificar banco do
  laboratório. O teste não é comprovação experimental com animais reais.

# Calibração de descoberta e evento de entrada (US-12/US-13)

Implementação local sobre a trajetória da US-09/10. O algoritmo de descoberta
da US-11 permanece inalterado; cada ajuste usa outro conteúdo YAML e gera nova
evidência. `barnes.yaml`, nos cards, corresponde à configuração operacional:
este repositório usa `configs/default.yaml`, ou outro arquivo passado por `--config`.

**Situação em 05/11/2026:** entrega D3, data acordada, observador e trial de
referência não confirmados. C2/G3 também não confirmados. A calibração real da
US-12 está bloqueada por dependência externa. Os testes sintéticos verificam
o software e não substituem essa entrega nem o aceite do cliente.

## Preparação

1. Instalar as dependências do projeto: `uv sync --locked`.
2. Configurar o PostgreSQL e executar `uv run barnes db migrate`. A migração
   `0009_us13_entry_details.sql` acrescenta os detalhes de entrada; eventos
   existentes continuam válidos com detalhes vazios.
3. Ter o trial cadastrado com intervalo útil, rotação, montagem, escala e
   trajetória gerada por `barnes pose series`/`pose review`.
4. Receber D3 do observador treinado do laboratório e confirmar C1/C2 com o
   responsável por G3. Não produzir rótulos improvisados para destravar o aceite.

O processamento compara identidade do trial/vídeo/execução, escala e recorte
da série com o banco. Mudou a escala ou o recorte? Regenere a série. Recalcular
eventos lê o Parquet, sem abrir ou decodificar o vídeo. A checagem física do vídeo
pertence à geração da série; o relatório identifica essa limitação explicitamente.

## Critério de entrada implementado, sujeito à confirmação C2/G3

```yaml
entrar:
  focinho_dentro: true
  raio_fator: null
  duracao_minima_s: null
```

`raio_fator` multiplica o raio de cada buraco cadastrado na montagem, convertido
para cm pela escala calibrada. A fronteira pertence à área. O fator e a duração
devem ser números positivos e finitos; `null` impede executar a detecção. Nenhum
valor numérico de produção foi presumido. `focinho_dentro: false` não corresponde
ao detector disponível e é recusado.

A entrada é confirmada quando um segmento de quadros consecutivos apresenta o
focinho válido dentro da área por pelo menos `duracao_minima_s`. A duração é a
diferença entre os tempos observados, sem contar um quadro isolado como duração
positiva. Sair da área, perder o focinho ou saltar um quadro interrompe o segmento.
A ausência do centro do corpo não apaga um focinho observado, mas pode impedir o
cálculo da distância. A interpolação já feita e identificada pela US-10 é mantida;
este estágio não preenche lacunas.

**Convenção temporal proposta para G3:** `t_E` é o primeiro quadro do segmento
que depois alcança a duração mínima. `confirmed_at_s` informa o momento em que
essa duração foi comprovada. Toques curtos não geram E. Permanecer dentro gera
uma entrada; sair e entrar novamente pode gerar outra. Não há inferência de
continuidade além das amostras disponíveis.

Cada E é associado à primeira descoberta D do mesmo buraco e trial. D e E no
mesmo quadro produzem hesitação zero, devido à resolução amostral. D ausente ou
posterior a E gera inconsistência com trial e buraco; o evento E é preservado e
seus deltas ficam ausentes. Essa convenção de simultaneidade também deve ser
confirmada em G3.

As distâncias são comprimentos do caminho do **centro do corpo**, somando os
segmentos entre amostras, e não distâncias em linha reta entre buracos:

| Campo de exportação | Definição | Unidade |
|---|---|---|
| `delta_latency` | `t_E - t_D` | s |
| `delta_distance` | Caminho do centro entre os quadros D e E | cm |
| `total_latency` | `t_E` desde o início do intervalo útil, para o alvo | s |
| `total_distance` | Caminho do centro desde a primeira amostra útil até E, para o alvo | cm |

Nos detalhes JSON/banco, as distâncias usam nomes `delta_distance_cm` e
`total_distance_cm`. O resumo do trial usa a **primeira entrada no alvo vigente**,
resolvido pela rotação do trial. Reentradas permanecem nas linhas de eventos,
referidas à primeira D daquele buraco. Sem entrada no alvo, `total_event=false`
e os tempos/distâncias correspondentes ficam `null`; não se inventa sucesso
no fim do vídeo. O contrato completo de censura/exportação estatística é da US-25.

Lacunas do centro ou quadros ausentes no percurso tornam a distância `null`, com
motivo em `issues`. Não se soma apenas o trecho disponível para apresentar uma
distância menor. Um `null` no JSON vira campo vazio no CSV, nunca zero implícito.
Os artefatos carregam a marca de qualidade da US-10 e a proveniência da série;
qualidade desconhecida é `nao_avaliada` no CSV.

## Executar entrada

Após preencher C1/C2 em uma configuração identificada:

```powershell
uv run barnes events enter --trial 1 --config configs/default.yaml
```

O número 1 é ilustrativo: use o ID do trial real. O comando cria
`data/events/entry-<uuid>/events.json` e `entries.csv`, registra `execucao` e os
eventos D/E na mesma transação. Cada nova execução preserva as anteriores;
ao consultar `evento_buraco`, filtre por `execucao_id` para não somar rodadas.
Uma falha de exportação/commit desfaz a tentativa e remove seus arquivos.
Execuções com inconsistência ficam registradas e retornam código **2**.

## Formato de entrega D3

Guardar o arquivo original do laboratório e produzir uma transcrição fiel em
JSON. A identificação do observador registra quem fez a anotação; o software
não autentica sua qualificação. A fonte deve permitir recuperar a entrega
original. Campos obrigatórios:

| Campo | Conteúdo |
|---|---|
| `schema_version` | `1` (opcional) |
| `trial_id` | ID positivo do trial no banco |
| `observer` | Identificação do observador treinado do laboratório |
| `source` | Referência à entrega original; `reference` é alias aceito |
| `delivered_on` | Data real da entrega, `AAAA-MM-DD` |
| `time_origin` | `intervalo_util` |
| `video_sha256` | Hash completo do vídeo, se fornecido (opcional) |
| `events` | Lista não vazia de `{tipo, hole_number, t_s}` |

`tipo` é `descoberta` ou `entrada`; `hole_number` é o índice físico **0..N−1**,
não o ID da linha `holes`. `t_s` é tempo não negativo em segundos desde o início
do intervalo útil. Se D3 usa o início do vídeo, converter os tempos explicitamente
e preservar a entrega original; não há conversão silenciosa.

É aceita uma descoberta por buraco, como na US-11, e múltiplas entradas em tempos
distintos. Duplicatas, números inválidos, trial/vídeo incompatíveis, buracos
inexistentes e tempos fora do intervalo são recusados. Um arquivo sem eventos
do tipo solicitado não serve como referência positiva de calibração.

## Rodadas de calibração

```powershell
# Sem D3: registra bloqueio e termina com código 2; não acessa o banco.
uv run barnes events calibrate --trial 1 --kind descoberta

# Com a entrega real: cada execução registra uma rodada nova.
uv run barnes events calibrate --trial 1 --kind descoberta --annotations data/annotations/d3.json --config configs/default.yaml
uv run barnes events calibrate --trial 1 --kind entrada --annotations data/annotations/d3.json --config configs/default.yaml
```

Saídas: `data/calibration/events/<uuid>.json` e `.md` (ou diretório `--out`).
Cada rodada guarda limiares completos, erros por ocorrência, hashes dos arquivos,
geometria/escala/recorte, versão do código, ambiente, máquina, observador, fonte e
data de D3, além de `execucao_id` quando houve processamento. Git sujo ou desconhecido
gera aviso e permanece registrado; para uma evidência reproduzível, use código commitado.

O pareamento é **por buraco, tipo e ordem cronológica**, um evento de cada lado.
Não se procura o vizinho temporal mais próximo. Cada par precisa cumprir
`abs(automático − manual) <= 0.5 s` para descoberta, ou `<= 0.3 s` para entrada.
Uma média pequena não compensa um evento fora da tolerância. Eventos faltantes
ou extras são mostrados e reprovam a rodada. D3 deve cobrir todos os eventos do
tipo avaliado no trial; não utilizar uma amostra parcial como lista completa.

Modificar **somente o YAML** entre rodadas e executar novamente. O comando não
reescreve US-11, não escolhe sozinho limiares e não transforma `calibrado_contra_anotacao`
em `true`. Os estados possíveis são:

| Estado | Significado e próximo passo |
|---|---|
| `blocked_missing_d3` | Entrega não disponível/confirmada; acertar a dependência externa |
| `passed` | Todos os pares desta rodada cumprem a tolerância e não há inconsistência D→E |
| `divergence_review_required` | Rever os desvios/contagens/inconsistências e a definição operacional com o laboratório |

Se nenhuma combinação **testada** convergir, levar o histórico ao cliente e
registrar a discussão como divergência de definição operacional. Um resultado
negativo isolado não prova que nenhuma combinação possível converge. Os comandos
preparam essa evidência local; não enviam mensagens nem concedem aceite G3.

## Incorporar evidência e obter aceite

```powershell
uv run barnes events calibration-evidence data/calibration/events/<uuid>.json
```

Substituir `<uuid>` pelo identificador real. O comando acrescenta a rodada,
incluindo limiares e comparações, a `docs/definicoes-metricas.md`; uma segunda
inclusão do mesmo ID é recusada. Também aceita `--document` para preparar uma
cópia de revisão. Revise o conteúdo, registre qual rodada e conjunto de limiares
foram escolhidos, obtenha a resposta escrita do decisor e preencha G3. Uma rodada
aprovada numericamente não equivale a aprovação do cliente.

Os artefatos em `data/` ficam fora do Git. Preserve-os na infraestrutura local
do grupo, inclusive D3 original. A evidência incorporada aos documentos pode
ser commitada após revisão dos dados que serão compartilhados.

## Testes

```powershell
uv run --no-sync python -m pytest tests/events/ tests/db/test_hole_events.py
uv run --no-sync python -m pytest
uv run --no-sync python -m ruff check src/ tests/
```

Os testes de CLI usam Parquet real e uma fronteira de banco simulada para conferir
exportação, identidade, rollback e história. Além deles,
`tests/events/test_cli_events_postgres.py` executa os comandos completos com
PostgreSQL real, sem simular as funções de persistência: confere os eventos e a
execução gravados, os arquivos CSV/JSON e o rollback após falha de exportação.

Os testes SQL reais precisam de `BARNES_TEST_DATABASE_URL` e das migrações aplicadas
no banco descartável. São pulados quando esse banco não está configurado; não
usam o banco de trabalho. A integração foi executada localmente em PostgreSQL
16.15 em 06/11/2026; veja [a evidência técnica](validacao-us12-us13-postgres.md).

# Contrato da sequência de visitação (US-15)

**Versão do contrato: 1** · código: `src/barnes/events/sequence.py` · gerado por
`barnes events sequence`, a partir de `evento_buraco` já persistido pela US-13/US-14
(`barnes events enter`).

A sequência de visitação é a lista cronológica das checagens de buraco de um trial —
**checagem = entrada confirmada (E, US-13)**, não a simples descoberta (D, US-11):
notar um buraco de longe não é checá-lo. É a **entrada canônica dos Épicos E (erros,
US-17) e F (estratégia, US-20)**: nenhum dos dois deve reabrir a trajetória de pose
(RN03) — ambos leem só a sequência.

Não existe tabela própria. "Persistida" aqui quer dizer: reconstruída
deterministicamente a partir de linhas já persistidas em `evento_buraco` (que já
carregam, em `details`, a descoberta pareada e o dwell da US-13/14) — a mesma
filosofia de `qualidade_pose` (VIEW, nunca uma marca guardada) e do próprio
`compute_errors` (US-17), que também não tem tabela.

## Campos (`SequenceItem`)

| Campo | Tipo | Significado |
|---|---|---|
| `ordem` | int | posição na sequência, 1-based |
| `buraco_platform` | int | índice do buraco na montagem, 0..N-1 |
| `angulo_deg_room` | float | posição do buraco **no referencial da sala** (US-05, `hole_to_room_angle`), [0, 360) |
| `inicio_s` | float | início da checagem — chave de ordenação (ver abaixo) |
| `t_descoberta_s` | float \| `None` | tempo da descoberta pareada (US-11), **sempre exibido**, mesmo numa reentrada; `None` numa entrada órfã, sem D anterior ou simultânea |
| `t_entrada_s` | float | tempo de início da entrada confirmada (US-13) |
| `dwell_s` | float | permanência da checagem, em segundos (US-14) |
| `dwell_interpolado` | bool | o dwell toca algum quadro interpolado pela US-10 |
| `alvo` | bool | o buraco é o buraco-alvo do trial |
| `issues` | tuple[str, ...] | inconsistências herdadas do `EntryEvent` de origem (US-13) |

**`inicio_s` só usa `t_descoberta_s` na primeira visita cronológica a cada
buraco.** A descoberta (US-11) é detectada uma vez por buraco, não uma vez
por visita; reentradas (preservadas pela US-13) começam no próprio
`t_entrada_s`, porque a descoberta já foi "gasta" pela primeira visita — do
contrário, duas checagens do mesmo buraco colidiriam no mesmo instante e a
ordem estritamente crescente (RN01) seria impossível. `t_descoberta_s`
continua populado nas duas (é a descoberta do buraco, exibida para
contexto), mas só o item da primeira visita tem `inicio_s == t_descoberta_s`.
É a mesma chave usada para ordenar e para `VisitItem.inicio_s` (ver abaixo) —
usar tempos diferentes para as duas coisas seria uma armadilha. Este caso foi
pego numa conferência manual contra um trial de referência real, não
imaginado em abstrato.

## Como é montada

`build_sequence(entries, *, geometry, rotation_deg, target_hole_number=None)`:

1. Recebe as `EntryEvent` do trial — na prática, as linhas `tipo='entrada'` de
   `evento_buraco` da **execução de eventos mais recente** (`barnes events enter`
   mais recente; recalibrar não mistura rodadas diferentes na mesma sequência).
2. Converte cada `hole_number` para o referencial da sala com a rotação do trial
   (`hole_to_room_angle`, US-05).
3. Ordena por `inicio_s` e numera `ordem` a partir de 1.
4. Recusa (`SequenceError`) duas checagens com o mesmo `inicio_s` — não resolve o
   empate em silêncio, porque indica defeito de quem produziu os eventos.

Uma lista vazia de entradas é aceita: trial sem nenhuma checagem é um resultado
real (RN01), não um erro.

## Projeção para o US-17/US-20 (RN03)

`to_visit_sequence(items)` devolve `barnes.metrics.errors.VisitSequence` —
**já implementado e testado** (`compute_errors`, `tests/metrics/test_errors.py`),
que só aceita `VisitItem(buraco_platform, angulo_deg_room, inicio_s, dwell_s, alvo)`.
Isto é literalmente o RN03 em código: quem for calcular erros (US-17, já existe, só
falta plugar numa CLI) ou estratégia (US-20, ainda não implementado) deve passar
por aqui, nunca reler o Parquet de trajetória nem `evento_buraco` diretamente.

```python
from barnes.events.sequence import build_sequence, to_visit_sequence
from barnes.metrics.errors import compute_errors, load_error_definition

items = build_sequence(entries, geometry=geometry, rotation_deg=rotation_deg)
erros = compute_errors(to_visit_sequence(items), load_error_definition())
```

## Invariantes verificadas em código

Um `SequenceError` recusa, em vez de montar uma sequência ambígua:

- montagem com mais de um buraco-alvo (sem `target_hole_number` explícito), ou
  nenhum;
- `target_hole_number` ou `hole_number` de uma entrada fora da montagem;
- ordem não **estritamente** crescente de `inicio_s` (RN01).

`to_visit_sequence` não duplica essas checagens: `VisitSequence.avaliada` já
valida ordem estrita e alvo único por conta própria (US-17).

## Concordância com anotação manual (RN04)

`compare_sequence(manual, automatic)` compara a sequência automática (lista de
`buraco_platform`) com a sequência de `hole_number` dos eventos `tipo="entrada"`
do mesmo D3 já usado pela US-12/13 (`barnes.events.calibration.ManualAnnotations`
— nenhum formato novo de anotação). Concordância = fração de posições
coincidentes, sobre o tamanho da maior sequência; sequências de tamanhos
diferentes nunca são truncadas em silêncio. Critério de aceite: concordância
≥ 0,95. Sem D3 entregue, `blocked_sequence_round` registra a dependência externa
— mesmo tratamento D3-bloqueado do US-12/13
(`docs/eventos-calibracao-entrada.md`), nunca um rótulo improvisado.

## Como ler

```bash
uv run barnes events sequence --trial 12
uv run barnes events sequence --trial 12 --annotations data/annotations/d3.json
```

Saída em `data/events/sequence-<uuid>/`: `sequencia.csv` (tabular, RN01),
`sequence.json` (mesmo conteúdo, com `source_execucao_id`) e, com
`--annotations`, `comparacao.json` (RN04). Sai com código 2 se a concordância
for `< 0,95` ou se o D3 estiver ausente/for de outro trial.

## Quem consome e como

| História | Usa |
|---|---|
| US-17 (erros, já implementado) | `to_visit_sequence` → `compute_errors`; nunca reabre a trajetória (RN02/RN03 do US-17) |
| US-20 (estratégia, pendente) | precisará da mesma sequência, no referencial da sala, para adjacência angular entre checagens consecutivas (RN05 do US-20) |

## Mudanças

Mudança compatível (ex.: campo novo opcional em `SequenceItem`): mantém a versão
e atualiza este documento. Mudança incompatível (renomear/remover um campo, ou
mudar a regra de `inicio_s`/ordenação): avise quem for implementar US-17 numa CLI
de verdade e quem for implementar US-20 — RN05 exige aviso à equipe antes de
alterar o contrato fixado no Sprint 1.

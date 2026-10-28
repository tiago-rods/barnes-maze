# Contrato da trajetória de pose por trial (US-09, US-10)

**Versão do contrato: 1** · código: `src/barnes/pose/trajectory.py` (esquema verificado
na escrita e na leitura) · gerado por `barnes pose series` e regenerado por
`barnes pose review`.

A trajetória de cada trial fica em **`data/interim/trial_<trial_id>.parquet`**, um
arquivo por trial (US-09 RN04). Ela é a entrada de todo o Épico D (eventos por
buraco), da qualidade de pose (US-10) e das métricas que leem posição ou orientação.
**Ninguém deve ler o `pose.csv` da inferência diretamente**: ele está em pixels, com
tempo desde o início do vídeo e sem escala.

Reprocessar um trial sobrescreve o arquivo. O histórico fica na tabela `execucao`
(US-27): a coluna `execucao_id` diz qual execução gerou o arquivo, e
`barnes execution show <id>` mostra modelo, limiares, parâmetros e commit.
`trials.trajectory_path` aponta para o arquivo atual.

## Colunas

Uma linha **por quadro do intervalo útil** (US-03), contígua: nenhum quadro é omitido,
nem quando a pose está ausente.

| Coluna | Tipo | Significado |
|---|---|---|
| `trial_id` | int32 | `trials.id` (constante no arquivo) |
| `execucao_id` | int32 | `execucao.id` que gerou o arquivo (constante) |
| `quadro` | int32 | índice do quadro no vídeo original, contíguo e crescente |
| `t_s` | float64 | segundos **desde o início do intervalo útil** (soltura) = `quadro / fps_real − intervalo_inicio_s` |
| `focinho_x_cm_image`, `focinho_y_cm_image` | float64 | focinho, em cm |
| `centro_corpo_x_cm_image`, `centro_corpo_y_cm_image` | float64 | centro do corpo, em cm |
| `base_cauda_x_cm_image`, `base_cauda_y_cm_image` | float64 | base da cauda, em cm |
| `focinho_confianca`, `centro_corpo_confianca`, `base_cauda_confianca` | float64 | score bruto do modelo (NaN se o modelo não informou) |
| `focinho_valido`, `centro_corpo_valido`, `base_cauda_valido` | bool | o ponto tem x e y (detectado, corrigido à mão ou interpolado) |
| `pose_valida` | bool | focinho **e** centro do corpo válidos, e distintos: há θ |
| `theta_deg_image` | float64 | orientação da cabeça, em graus, [0, 360); NaN sem `pose_valida` |
| `interpolado` | bool | algum ponto desta linha foi preenchido por interpolação (US-10 RN01) |
| `fps_variavel` | bool | o vídeo tem fps variável (US-01): **`t_s` é aproximado** (constante) |

**Posição em cm nos eixos da imagem** (sufixo `_image`, US-05 RN05): a mesma origem
dos pixels, no canto superior esquerdo do quadro, com **y crescendo para baixo**. É o
pixel, **suavizado** pela US-10 (ver abaixo), multiplicado pela escala da montagem
(US-02, `cm_per_px`). Para comparar com os buracos, converta `holes.x_px/y_px` com o
mesmo `cm_per_px` dos metadados. Para o referencial da sala, use
`barnes.geometry.reference_frame` (US-05).

**Ausência é dado** (US-09 RN05): ponto não detectado fica `NaN`, com `*_valido = false`.
**Nunca** há repetição do quadro anterior nem valor nulo. Só a US-10 preenche, e só
lacunas curtas: a linha preenchida fica com `interpolado = true`, e o relatório do
preenchimento vai no metadado `pos_processamento`.

## Orientação da cabeça θ

`theta_deg_image` é a direção do vetor **centro do corpo → focinho**:

```
θ = atan2(y_focinho − y_centro, x_focinho − x_centro)  em graus, levado a [0, 360)
```

Com y para baixo, isso dá **0° apontando para a direita da imagem (+x) e ângulos
crescendo no sentido horário na tela** (90° = para baixo na imagem). É a mesma
convenção de `holes.angle_deg` (US-04) e dos referenciais da US-05, fixada em
`docs/definicoes-metricas.md` §6.5. Um ângulo de cabeça→buraco (US-11) pode, portanto,
ser comparado diretamente com `holes.angle_deg`.

Tolerância de verificação (US-09 Cenário 2, testes em `tests/pose/test_series.py`): em
trajetórias sintéticas retas nas 8 direções, θ coincide com a direção de deslocamento
com erro < 1e-6° sem ruído. Com ruído gaussiano de 1 px num eixo de corpo de 20 px, o
desvio mediano é ≤ 5°. É tolerância de **teste** do cálculo, não um limiar do laboratório.

## Metadados do arquivo

Gravados como JSON no esquema Parquet (chave `barnes.trajetoria`):
`contrato_versao`, `trial_id`, `execucao_id`, `content_hash` (vídeo, US-01), `model_id`
(pesos da US-07), `fps_real`, `fps_variavel`, `cm_per_px`, `px_per_10cm`,
`intervalo_inicio_s`, `intervalo_fim_s` (segundos desde o início do vídeo),
`convencao_angular` (texto) e `gerado_em` (UTC).

Opcional (US-10): `pos_processamento`, o relatório de qualidade da pose. Traz
`cobertura` (os três pontos, contando interpolados e corrigidos), `cobertura_deteccao`
(só o que o modelo detectou), `cobertura_minima`, `qualidade` (`suficiente`,
`revisao_pendente` ou `insuficiente`), `quadros_interpolados`, `fracao_interpolada`,
`quadros_corrigidos`, `correcoes_ignoradas`, `trechos_sinalizados` (lista de
`{inicio, fim, pontos, pendente}`, em quadros do vídeo), `trechos_pendentes`, os
`parametros` usados e `ressalva_fps_variavel` (texto ou `null`, US-10 RN07).

## Invariantes verificadas em código

Um arquivo que viole qualquer uma é recusado com `TrajectoryContractError`, na escrita
**e** na leitura:

- esquema idêntico ao da tabela acima (nomes, tipos e ordem) e nenhum valor nulo;
- `contrato_versao` igual à do código, e todos os metadados obrigatórios presentes;
- `trial_id`, `execucao_id` e `fps_variavel` constantes e iguais aos metadados;
- `quadro` contíguo e crescente; `t_s` finito e estritamente crescente;
- `*_valido` verdadeiro exatamente quando x e y são finitos;
- `pose_valida` só com focinho e centro válidos; θ finito exatamente quando
  `pose_valida`, e sempre em [0, 360);
- `pos_processamento`, se existir, é um objeto; e **linha com `interpolado` exige
  `pos_processamento`** (todo preenchimento fica registrado).

## Pós-processamento (US-10)

`barnes pose series` monta a série sempre a partir do `pose.csv` da inferência, das
correções manuais do trial (tabela `correcao_pose`) e dos parâmetros da seção `pose:` de
`configs/default.yaml`. Por isso regenerar dá o mesmo resultado e nunca suaviza duas
vezes. A ordem é sempre esta (`barnes.pose.quality.postprocess_pose`, em pixels, antes
da conversão para cm):

1. **Correções manuais** sobrepõem o ponto no quadro (vale a da revisão mais recente).
   O ponto corrigido perde a confiança do modelo (`*_confianca` = NaN).
2. **Suavização** por mediana móvel (`suavizacao.janela_quadros`, ímpar; 1 = nenhuma),
   por ponto, só dentro de trechos contínuos com o ponto. A janela encolhe
   simetricamente nas pontas do trecho e nunca atravessa uma lacuna. Remove um quadro
   isolado muito fora e preserva movimento retilíneo. θ é recalculado dos pontos
   suavizados.
3. **Interpolação linear** (por índice de quadro) das lacunas **curtas**: até
   `lacuna_curta_max_quadros` quadros seguidos sem um ponto, com o ponto presente nos
   dois lados. A confiança continua NaN e a linha recebe `interpolado = true`.
4. **Sinalização** das lacunas restantes: as **longas** (maiores que o limite) e as que
   tocam a **borda** do intervalo útil, que não têm um dos lados para interpolar.
   Lacunas de pontos diferentes que se encostam viram um trecho só. Um trecho fica
   `pendente` até ser dado por revisado em `barnes pose review`.
5. **Cobertura**: fração dos quadros do intervalo com os três pontos (detectados,
   corrigidos ou interpolados). A qualidade é `revisao_pendente` enquanto houver trecho
   pendente; sem pendência, é `insuficiente` abaixo de `cobertura_minima` e
   `suficiente` caso contrário.

As lacunas são detectadas **por ponto**: faltar só a base da cauda por dois quadros
preenche só a base da cauda. Com `fps_variavel`, a interpolação é menos exata (os tempos
já são aproximados), e o relatório leva `ressalva_fps_variavel` (US-10 RN07). A US-01 só
detecta fps variável por trial, não por trecho.

## Como ler

```python
from barnes.pose.trajectory import read_metadata, read_trajectory

table = read_trajectory("data/interim/trial_12.parquet")  # valida o contrato
meta = read_metadata(table)
df = table.to_pandas()
```

Coordenada ausente é **NaN, não NULL**. Em SQL, NaN contamina agregações
(`avg(theta_deg_image)` dá NaN), então filtre com `WHERE pose_valida` (ou
`*_valido`) antes de agregar.

```sql
-- DuckDB, sem validar (para explorar):
SELECT count(*) AS quadros, sum(CASE WHEN pose_valida THEN 0 ELSE 1 END) AS sem_pose
FROM 'data/interim/trial_12.parquet';

SELECT avg(theta_deg_image) FROM 'data/interim/trial_12.parquet' WHERE pose_valida;
```

## Quem consome e como

| História | Usa |
|---|---|
| US-10 (qualidade de pose) | produz a série: preenche lacunas curtas e marca `interpolado`, sinaliza as longas, grava `pos_processamento` e a cobertura em `trials.cobertura_pose`; `fps_variavel` acompanha o relato (RN07) |
| US-11 (descoberta) | `focinho_*_cm_image` para a distância focinho→buraco; `theta_deg_image` para o ângulo cabeça→buraco; `quadro`/`t_s` vão para `evento_buraco`; `interpolado` para marcar evento sobre dado reconstruído |
| Métricas (US-15 em diante) | posições em cm e `t_s`; velocidade com ressalva quando `fps_variavel`; fração interpolada (`interpolado`) junto da métrica (US-18 RN04); trial de qualidade insuficiente marcado (VIEW `qualidade_pose`) |

## Mudanças

Mudança compatível (ex.: metadado novo opcional): mantém a versão e atualiza este
documento. A US-10 foi uma mudança compatível: `interpolado` passou a ser usado como
estava previsto, as posições passaram a ser suavizadas e entrou o metadado opcional
`pos_processamento`. A versão continua 1. Mudança incompatível (renomear, remover ou mudar o tipo de uma coluna ou o
significado de um campo): incremente `CONTRACT_VERSION` em `trajectory.py`, atualize
este documento e avise as equipes de eventos, métricas e estratégia.

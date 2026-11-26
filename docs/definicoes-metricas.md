# Definições operacionais das métricas

**Marco M1 · portão G3 · status: RASCUNHO — não assinado**

Este documento fixa o que cada métrica significa **no laboratório**, não no
código. Ele é a fonte dos valores de `configs/default.yaml`.

> **Por que este documento existe.** Quase toda métrica do escopo depende de uma
> definição operacional que ainda não existe. "Tempo de encontrar o buraco" é o
> primeiro momento em que a cabeça se orienta e se aproxima o suficiente —
> mas 5 cm e 30° produzem uma latência, 10 cm e 45° produzem outra, e no mesmo
> vídeo. A diferença não é pequena: um animal contornando a borda passa perto de
> muitos buracos sem checar nenhum.
>
> Se estes limiares forem escolhidos pela equipe por conveniência, o software
> produz números coerentes, plausíveis, bem formatados — e sem relação com o que
> o laboratório chama de latência.
>
> **Nada aqui é decidido pela equipe.** Os valores vêm do Bloco C do
> questionário, são calibrados contra anotação manual (US-12, US-13) e
> aceitos por escrito por quem decide (C6). Esta é a única defesa do grupo se,
> na semana 9, alguém disser que a latência está errada.

> **Atualização de 12/11/2026 — sem contato com o laboratório.** O contato com o
> LNBio não ocorreu, e este documento não será assinado (G3 não fecha). Para o
> software produzir resultados, a equipe aprovou valores próprios para os
> limiares abaixo, com a justificativa de cada um em
> [`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md). Eles estão em
> `configs/default.yaml` marcados como decisão da equipe
> (`versao_definicoes: decisoes-equipe-2026-11-12-sem-G3`), não foram calibrados
> contra anotação manual e entram no relatório como limitação. A defesa do
> parágrafo acima continua valendo: são convenções da equipe, não o que o
> laboratório chama de latência.

## 1. Limiares a acordar

| # | Parâmetro | Chave em `default.yaml` | Valor em uso | Origem | Status |
|---|---|---|---|---|---|
| 1 | Distância para "encontrar" | `encontrar.distancia_cm` | 3 cm (provisório) | C1 | provisório (sem G3) |
| 2 | Ângulo de orientação da cabeça | `encontrar.angulo_graus` | 30° (provisório) | C1 | provisório (sem G3) |
| 3 | Critério de "entrar" | `entrar.focinho_dentro` | focinho dentro | C2 | decisão da equipe (sem G3), §7 |
| 3a | Área de entrada, como fator do raio físico calibrado | `entrar.raio_fator` | 1,0 | C2 | decisão da equipe (sem G3), §7 |
| 4 | Duração mínima de entrada | `entrar.duracao_minima_s` | 0,2 s | C2 | decisão da equipe (sem G3), §7 |
| 5 | Duração mínima de dwell | `dwell.duracao_minima_s` | — (não é lida) | C2 | decisão da equipe: `null`, §7 |
| 6 | O que conta como erro | `erro.criterio` | qualquer buraco incorreto | C3 | decisão da equipe (sem G3), §8 |
| 7 | Duração mínima do erro | `erro.duracao_minima_s` | — (não se aplica) | C3 | decisão da equipe: `null`, §8 |
| 8 | Estratégia — cruzamentos do centro | `estrategia.cruzamentos_centro_min` | 1 | C4 | decisão da equipe (sem G3), §10 |
| 9 | Estratégia — adjacência angular | `estrategia.adjacencia_angular_graus` | 18° (20 buracos) | C4 · B2 | decisão da equipe (sem G3), §10 |
| 10 | Estratégia — erros até o alvo | `estrategia.erros_ate_alvo_max` | 3 | C4 | decisão da equipe (sem G3), §10 |
| 11 | Estratégia — entropia máxima | `estrategia.entropia_max_espacial` | — | C4 | decisão da equipe: `null`, §10 |
| 11a | Estratégia — raio da zona central (cruzamentos) | `estrategia.centro_zona_raio_frac` | 0,5 | C4 (US-20) | decisão da equipe (sem G3), §10 |
| 11b | Estratégia — mínimo de buracos para "serial" | `estrategia.serial_min_buracos` | 2 | C4 (US-20) | decisão da equipe (sem G3), §10 |
| 12 | Tempo limite do trial | `trial.tempo_limite_s` | 180 s | B5 | decisão da equipe (sem G3), §6 |
| 13 | Frequência esperada mínima para o qui-quadrado (US-23) | `estatistica.frequencia_esperada_minima` | — (`null`) | estatístico · B1 | **pendente**: sem valor, o teste não é escolhido |

As seções (§) da coluna Status são de `decisoes-sem-laboratorio.md`.

> **US-11 (linhas 1-2) — valor PROVISÓRIO, não é o aceite de G3.** O cálculo de
> distância focinho→buraco e do ângulo de orientação da cabeça, o carregamento
> parametrizado dos dois limiares e a persistência do evento de descoberta em
> `evento_buraco` já estão implementados e testados (`barnes.events.discovery`,
> `tests/events/test_discovery.py`, `barnes events discover`).
>
> Como o laboratório ainda não respondeu C1, preenchemos `encontrar.distancia_cm`
> (3 cm) e `encontrar.angulo_graus` (30°) com uma faixa comum de rastreamento
> comportamental de roedores (ex. zonas de "nose-point"/orientação de cabeça do
> EthoVision) para não travar o desenvolvimento — **não é uma citação
> verificada**, nenhum artigo específico foi conferido para este número, e não
> é o valor acordado pelo laboratório. `encontrar.calibrado_contra_anotacao`
> continua `false` de propósito (nunca marque este valor como aceito). Status
> "provisório (sem G3)" acima — **não mude para "acordado"/"concluído" até o
> laboratório responder C1** e, então, até a calibração da [US-12] confirmar a
> diferença ≤ 0,5 s contra a anotação manual.

## 2. Definições em prosa

Preencher **com as palavras do laboratório**, não com as nossas.

### Encontrar
_A definir em G3._

### Entrar / checar fisicamente
_A definir em G3._

### Erro
_A definir em G3._

> **US-17 — nota de implementação, não é a definição do laboratório
> (`barnes.metrics.errors`, `tests/metrics/test_errors.py`).** A definição acima
> continua em aberto; as linhas 6-7 seguem "pendente". O que está implementado é
> só o mecanismo, parametrizado pelas duas chaves de C3:
>
> - `erro.criterio = qualquer_buraco_incorreto`: toda checagem de buraco que não é
>   o alvo é um erro. `acima_de_duracao`: só a checagem incorreta com
>   dwell ≥ `erro.duracao_minima_s` (inclusivo). Enquanto `erro.criterio` estiver
>   `null`, a contagem é recusada com erro; nenhum valor provisório foi posto.
> - Fonte única: a **sequência de visitação** da US-15 (buraco na plataforma e
>   posição na sala, início da checagem, dwell, se é o alvo). O erro nunca relê a
>   trajetória nem o vídeo; trocar a definição é recalcular sobre a mesma
>   sequência (RN02, RN05). Como a US-15 ainda não existe, sem sequência o
>   resultado é "não calculado" (vazio), nunca "zero erros".
> - Cada checagem conta, inclusive a revisita a um buraco incorreto já checado.
>   Checagens do alvo nunca são erro. `total_errors` cobre o trial inteiro,
>   inclusive depois de achar o alvo.
> - `primary_errors` (erros até a descoberta do alvo): erros com início antes da
>   **primeira checagem do alvo** na sequência. Como cada item da sequência
>   começa no tempo de descoberta do buraco, esse corte é o evento D do alvo
>   (US-11 RN05, o mesmo de `primary_latency`), mas é lido da sequência. Se o
>   alvo não é checado, `primary_errors = total_errors`, marcado como censurado
>   (mesma lógica da censura: o trial não é descartado nem recebe zero).
> - Sob `acima_de_duracao`, uma checagem incorreta sem dwell medido (US-14)
>   impede o cálculo, com aviso: contá-la ou descartá-la seria inventar a duração.
>
> **C3 — decisão da equipe, sem o laboratório (12/11/2026,
> [`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §8):** critério
> `qualquer_buraco_incorreto`; revisitas contam como novos erros; o limite
> inclusivo não se aplica a esse critério; erros depois de achar o alvo entram em
> `total_errors`.

### Estratégias: aleatória, serial, espacial
_Não definido pelo laboratório (G3 não fecha). Decisão da equipe em 12/11/2026:
categorias de Harrison et al. (2006) — espacial, serial e aleatória —, com os
parâmetros da tabela da seção 1 (linhas 8-11b); ver
[`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §10. Sem anotação
manual, o kappa da US-21 não tem contra o que ser medido; o ferramental dele está
descrito na seção 4.4._

> **US-20 — implementação (`barnes.strategy.classification`, `barnes.strategy.signals`,
> `barnes.strategy.entropy`, `tests/strategy/`, `barnes strategy classify`).** Regra
> explícita, não modelo treinado (RN01): combina três sinais, todos calculados **até a
> primeira checagem do alvo** (ou o trial inteiro, marcado censurado, se o alvo não foi
> checado — mesma convenção de `primary_errors`, US-17):
>
> - **Cruzamentos do centro** (`barnes.strategy.signals.count_center_crossings`): número
>   de entradas na zona central da plataforma (raio = `estrategia.centro_zona_raio_frac`
>   × raio da circunferência dos buracos), na trajetória contínua (US-09). Rotação-invariante
>   — não depende do referencial da sala, porque o centro não se move com a rotação (US-05).
> - **Adjacência angular** (`barnes.strategy.signals.compute_angular_adjacency`): distância
>   angular circular do primeiro buraco checado até o alvo, e o comprimento da maior
>   sequência de buracos consecutivamente adjacentes entre si (`estrategia.adjacencia_angular_graus`),
>   no mesmo sentido (horário ou anti-horário). Opera sobre a **sequência de visitação da
>   US-15, no referencial da sala** (RN05) — nunca sobre a trajetória.
> - **Erros até o alvo** (`barnes.metrics.errors.compute_errors`, US-17): reusado sem
>   recálculo.
>
> **Regra de decisão:**
>
> - **Espacial** ⟺ erros ≤ `erros_ate_alvo_max` **e** primeiro buraco checado a ≤
>   `adjacencia_angular_graus` do alvo (ou nenhum buraco checado antes — foi direto) **e**
>   `cruzamentos < cruzamentos_centro_min`.
> - **Serial** ⟺ não é espacial **e** existe uma sequência de ≥ `serial_min_buracos`
>   buracos consecutivamente adjacentes, no mesmo sentido, antes do alvo **e**
>   `cruzamentos < cruzamentos_centro_min`.
> - **Aleatória** ⟺ nem espacial nem serial (sobra — decisão já escrita em §10).
> - **Não classificado** (`search_strategy = NULL`) se cruzamentos ou erros não puderam
>   ser calculados (sem pose válida, sem sequência) — nunca confundido com "aleatória"
>   (RN01: nenhuma categoria é um padrão/default).
>
> **Origem do critério (C4/RN04) e correção do Cenário 2 do card.** Sem contato com o
> laboratório, C4 é respondida com a citação de Harrison, F. A., et al. (2006),
> "Spatial and nonspatial escape strategies in the Barnes maze", *Learning & Memory*
> 13(6):809-816: a busca **aleatória** é definida ali, e replicada pela literatura
> derivada (Bhatt et al.; calculadoras/protocolos como ConductScience e bio-protocol),
> como a que cruza o centro da plataforma ou investiga os buracos sem sistema — nunca a
> espacial. O Cenário 2 de `docs/CARDS.md` ("foi diretamente ao alvo com poucos erros e
> **cruzando o centro**" → espacial) está em desacordo com essa citação; tratado como
> **inconsistência de redação do card**, não como regra — a implementação segue a
> literatura citada (0 cruzamentos tolerados para espacial, por padrão). Os demais três
> cenários do card (serial, aleatória, ajuste de limiar sem alteração de código) são
> reproduzidos tal como escritos, com um trial sintético por categoria em
> `tests/strategy/test_classification.py` (DoD "validar a classificação em um trial de
> cada categoria").
>
> **Entropia da trajetória** (`barnes.strategy.entropy.compute_trajectory_entropy`): índice
> separado, **não é um dos três sinais da regra** (RN02 lista só os três acima;
> `estrategia.entropia_max_espacial` continua `null` por decisão da equipe — fora da regra
> de Harrison, §10). Entropia de Shannon, em bits (base 2), da distribuição do **tempo**
> gasto pelo `centro_corpo` em setores angulares ao redor do centro da plataforma (padrão:
> um setor por buraco da montagem), na mesma janela "até o alvo". `None` (não calculada)
> sem amostra válida no trecho — nunca zero por omissão. Persistida em
> `trial_results.entropy_bits` (migração 0011, US-22) junto com `search_strategy`
> (coluna já existente desde a migração 0001).
>
> **Auditoria caso a caso (RN06):** os três sinais (cruzamentos, distância do primeiro
> buraco ao alvo, maior sequência adjacente, erros até o alvo) e os limiares usados vão
> para `execucao.metadata` e para um relatório JSON por execução de `strategy classify` —
> não há colunas novas em `trial_results` para eles, só `entropy_bits`/`search_strategy`.
>
> **Ajuste de limiar sem alteração de código (RN03, Cenário 4):** todos os limiares da
> regra — `cruzamentos_centro_min`, `adjacencia_angular_graus`, `erros_ate_alvo_max`,
> `centro_zona_raio_frac`, `serial_min_buracos` — ficam em `configs/default.yaml`, seção
> `estrategia`; alterar um valor e reexecutar `barnes strategy classify` produz a nova
> classificação sem tocar no código-fonte.

### Censura
Trial em que o animal não encontrou o alvo dentro do tempo limite. Marcado,
nunca descartado — exportado como `primary_event` e `total_event`.

> É a coluna que mais silenciosamente invalida a análise do cliente se sair
> errada: sem a marcação, os trials sem sucesso ou são descartados, enviesando o
> resultado, ou entram como se o animal tivesse achado no último segundo,
> enviesando na direção oposta.

> **US-16 — implementação (`barnes.metrics.latency`, `tests/metrics/test_latency.py`).**
> Evento observado até o tempo limite → `*_event = 1` e latência = tempo do evento;
> sem evento até o limite (ou evento depois dele) → `*_event = 0`, latência = tempo
> limite e distância = percorrida até o limite. Tempo zero = S (início do intervalo
> útil). Se `trial.tempo_limite_s` (linha 12, B5) estiver `null`, o cálculo é
> recusado com erro; desde 12/11/2026 ele vale 180 s por decisão da equipe
> ([`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §6). "Detector não
> executado" (hoje o de entrada, US-13) **não** é censura: `total_*` sai vazio, com
> aviso. Distância percorrida pelo `centro_corpo`, atravessando lacunas de pose em
> linha reta — ponto escolhido pela equipe, sem resposta do laboratório (§9).

### Distância total e velocidade média

> **US-18 — nota de implementação, não é a definição do laboratório
> (`barnes.metrics.displacement`, `tests/metrics/test_displacement.py`,
> `barnes metrics displacement`).**
>
> - **Uma** distância e **uma** velocidade média por trial, sobre o intervalo útil, a
>   partir da série da US-09. Não há velocidade por fase (ver SCRUM-223 abaixo).
> - Distância: soma dos segmentos do `centro_corpo` entre amostras válidas, com
>   lacunas atravessadas em linha reta. É a mesma regra e o mesmo ponto da US-16.
> - Velocidade média = distância ÷ tempo do **primeiro ao último ponto válido**
>   (decisão da equipe). Dividir pelo intervalo inteiro subestimaria a velocidade
>   sempre que falta pose numa borda. A duração do intervalo e o tempo sem pose nas
>   bordas saem junto.
> - Trechos interpolados pela US-10 entram, e a fração interpolada das amostras usadas
>   sai junto. A marca é por linha, então a fração é conservadora.
> - fps variável: a distância sai normal; a velocidade sai com a ressalva de base
>   temporal aproximada.
> - Sem amostra válida, distância e velocidade ficam vazias, nunca zero.
>
> **SCRUM-223 — velocidades por fase: derivadas pelo laboratório, não lidas do CSV
> (evidência no código; decisão da equipe, sem confirmação do laboratório).** O
> `barnes_maze.py` entregue
> pelo laboratório calcula as três velocidades a partir das colunas de distância e
> latência:
>
> - em `trials.csv`: `primary_speed = primary_distance / primary_latency` quando
>   `primary_event == 1`; `decision_speed = delta_distance / delta_latency` e
>   `total_speed = total_distance / total_latency` quando `primary_event == 1` e
>   `total_event == 1`;
> - em `probes.csv`: `primary_speed = primary_distance / primary_latency`,
>   `decision_speed = (total_distance − primary_distance) / (90 − primary_latency)` e
>   `total_speed = total_distance / 90`, com `probe_time = 90` fixo no código.
>
> Consequência: basta exportar as distâncias e latências (US-13, US-16, US-25), sem
> coluna de velocidade.
>
> | | |
> |---|---|
> | Resposta do laboratório | não houve contato com o LNBio |
> | Registro | decisão da equipe em 12/11/2026: `trials.csv` sem colunas de velocidade; probe de 90 s ([`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §3 e §11) |

### Eficiência de rota

> **US-19 — nota de implementação, não é a definição do laboratório
> (`barnes.metrics.efficiency`, `tests/metrics/test_efficiency.py`).** Convenções da
> equipe, sem resposta do laboratório:
>
> - **Índice** = distância percorrida até o alvo ÷ distância mínima da soltura ao alvo
>   (RN01). Mínimo teórico 1,0. Não é o `route_efficiency` da US-02 (ideal ÷ percorrida,
>   em [0, 1], coluna `trial_results.route_efficiency`), que continua como estava.
> - **Dois índices por trial**, como as latências da US-16: `primary_route_efficiency`
>   até a descoberta do alvo (D) e `total_route_efficiency` até a entrada (E). Qual dos
>   dois o laboratório chama de "eficiência de rota" fica em aberto. A distância
>   percorrida é a da US-16 (mesmo ponto, `centro_corpo`, lacunas em linha reta).
> - **Ponto de soltura** (RN02, SCRUM-228): a posição do centro do corpo na primeira
>   amostra válida do intervalo útil. O intervalo começa em S, a retirada do cilindro
>   (`decisoes-sem-laboratorio.md` §2), então a soltura é **medida** em cada trial, não
>   suposta no centro, e a resposta a B3 não muda o cálculo. Se falta pose no começo,
>   vale a primeira amostra com pose, com aviso. Sai junto a distância da soltura ao
>   centro da plataforma, para auditoria. Não há parâmetro novo.
> - **Distância mínima** (SCRUM-229): linha reta da soltura ao **ponto de chegada**, a
>   posição do centro do corpo na última amostra válida até D (ou E). Não é a distância
>   ao centro do buraco: o evento é detectado pelo focinho, e o centro do corpo para
>   alguns centímetros antes. Com o centro do buraco, um trajeto reto daria índice
>   < 1,0. Com o mesmo ponto nos dois extremos, a desigualdade triangular garante
>   índice ≥ 1,0. A distância da soltura ao centro do buraco-alvo sai junto, para
>   auditoria.
> - **Censura** (RN03): evento censurado na US-16 (`*_event = 0`) ou não calculado →
>   índice ausente (`None`), com aviso. Chegada no próprio ponto de soltura (distância
>   mínima zero) → ausente: a razão não é definida.
> - **Sanidade** (RN05): índice < 1,0 é recusado (`RouteEfficiencyError`). A tolerância
>   relativa é 1e-9. Em aritmética exata o índice nunca fica abaixo de 1. A soma de n
>   segmentos em ponto flutuante erra ~n · 2,2e-16 (~1e-12 em 180 s a 25 fps), e um
>   erro real de cálculo fica ordens de grandeza acima.
> - **Exportação** (RN04): `TrialRouteEfficiency.as_trial_results()` traz os dois
>   índices e a soltura (`release_x_cm_image`, `release_y_cm_image`, `release_t_s`,
>   `release_center_distance_cm`), em cm, para o final do `trials.csv` (US-25 converte
>   para metros). **Banco e CLI pendentes**, como nas US-16/17: a coluna
>   `route_efficiency` existente tem outra definição e `CHECK` 0..1, então gravar o
>   índice exige uma migração nova.
> - Validação (Cenários 1 e 2) com trajetórias sintéticas: rota reta do centro ao alvo
>   (índice 1,0, soltura no centro) e tigmotaxia (meia volta pela borda, índice > 3).
>   No trial de referência da US-28, o índice é 2,51.

### Distribuição de estratégias entre sessões

> **US-23 — nota de implementação (`barnes.stats.contingency`,
> `tests/stats/test_contingency.py`).** A entrada é uma lista mínima de pares (linha,
> estratégia), uma por trial, testada com dados sintéticos — `barnes.stats.contingency`
> continua sem ler o banco diretamente. Agora que a US-20 existe
> (`barnes.strategy.classification`, `trial_results.search_strategy` gravado por
> `barnes strategy classify`), quem monta essa lista a partir do banco lê
> `search_strategy` de cada trial; trials com `search_strategy IS NULL` (não
> classificado, RN01 da US-20) devem ser tratados como "estrategia = None" — fora da
> tabela, contados e avisados — nunca como uma quarta categoria.
>
> - **Categorias**: as três de Harrison et al. (2006) (§10 de
>   `decisoes-sem-laboratorio.md`), com os códigos do banco (`spatial`, `serial`,
>   `random`, `CHECK` da 0001). São parâmetro da função. Categoria sem nenhum trial
>   aparece com zeros e é sinalizada (Cenário 3). Estratégia desconhecida é recusada,
>   nunca descartada. Trial não classificado fica fora da tabela, contado.
> - **Linhas**: sessão (`trials.day_number`) ou grupo (RN04, B6 em aberto). O mesmo
>   procedimento serve aos dois (`dimensao`). Probes devem ficar de fora (não há alvo).
> - **Escolha do teste** (RN02, linha 13 da seção 1): se alguma frequência esperada
>   fica abaixo de `estatistica.frequencia_esperada_minima`, aplica-se Fisher; senão,
>   qui-quadrado de independência. É a regra do card (qualquer célula), mais estrita
>   que a de Cochran (nenhuma < 1 e no máximo 20% < 5). A escolha entre as duas fica
>   para o estatístico. **O limite fica `null`**: sem ele, a escolha é recusada.
> - Linhas e colunas inteiramente zeradas ficam na tabela reportada, mas **fora do
>   teste**. Frequência esperada zero deixa o qui-quadrado indefinido, e uma margem
>   zero não muda o Fisher. Com menos de 2 linhas ou 2 categorias com trials, não há
>   teste (`teste = None`), com justificativa.
> - **Fisher 2×2**: exato e bilateral (`scipy.stats.fisher_exact`), estatística =
>   razão de chances.
> - **Fisher R×C** (Fisher–Freeman–Halton): o `fisher_exact` clássico do SciPy é só
>   2×2. Desde a 1.15 ele aceita R×C com `method=MonteCarloMethod`: valor-p por Monte
>   Carlo sobre tabelas com as mesmas margens, estatística = probabilidade da tabela
>   observada. Sem `method`, o SciPy 1.17 também usa Monte Carlo, mas com semente
>   aleatória: o mesmo dado deu 0,175, 0,185 e 0,175 em três execuções. Por isso a
>   semente (0) e as reamostragens (99.999, erro-padrão ~0,0007 em p = 0,05) são fixas
>   e saem no resultado. São parâmetros do método numérico, não limiares. O piso do
>   SciPy no `pyproject.toml` subiu para 1.15.
> - **Qui-quadrado**: `scipy.stats.chi2_contingency`, com a correção de Yates padrão,
>   que só atua com 1 grau de liberdade. O uso fica registrado.
> - **Relato** (RN03): `IndependenceResult.as_record()` (JSON) e `render_markdown()`
>   trazem a tabela completa, o teste, a estatística, os graus de liberdade, o valor-p,
>   as frequências esperadas e a justificativa. Valor-p alto é resultado válido (RN05).

## 3. Protocolo de referência

| | |
|---|---|
| Artigo ou protocolo publicado a seguir (C5) | Decisão da equipe (12/11/2026, sem o laboratório): Sunyer et al. (2007) para o método (citação a conferir) e Harrison, F. A., et al. (2006), "Spatial and nonspatial escape strategies in the Barnes maze", *Learning & Memory* 13(6):809-816, para as estratégias — **citação verificada na US-20** (seção "Estratégias" acima; `decisoes-sem-laboratorio.md` §14) |

## 4. Calibração

Registro das rodadas de ajuste contra a anotação manual (US-12, US-13).

| Rodada | Data | Parâmetro | Valor testado | Diferença vs. anotação | Resultado |
|---|---|---|---|---|---|
| | | | | | |

Alvos: encontrar ≤ 0,5 s · entrar ≤ 0,3 s.

### 4.0 Calibração contra anotação manual: pulada (12/11/2026)

Não há anotação manual de Barnes maze: o laboratório não foi contatado, e a busca por
fontes públicas não encontrou nenhuma com pontuação humana
([`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §5.1). Por decisão
da equipe, **as comparações com anotação manual estão puladas**: a calibração da
US-12, as comparações da US-13, US-15, US-16 e US-17, o r ≥ 0,95 da US-18 e o kappa
da US-21. As seções 4.1 a 4.3 abaixo ficam como registro do ferramental, que
continua pronto caso uma anotação apareça. Nenhum limiar deste documento foi
calibrado contra anotação humana.

### 4.1 Situação da entrega US-12/US-13 em 05/11/2026

**D3: entrega não confirmada; calibração real bloqueada por dependência externa.**
Não foram fornecidos anotação, observador, trial de referência ou data acordada.
O responsável pelo projeto informou não ter conhecimento da entrega nem das
decisões C2/G3. Não há limiares finais ou erro experimental a registrar nesta
entrega. Os testes do software são sintéticos e não representam aceite.

O ferramental está implementado: `barnes events calibrate` compara cada
descoberta com tolerância inclusiva de 0,5 s e cada entrada com 0,3 s, preservando
erros assinados/absolutos, ausências e eventos extras. Entradas repetidas são
pareadas em ordem cronológica por buraco. Todas as ocorrências precisam passar;
uma média favorável não compensa uma ocorrência reprovada.

Cada rodada cria arquivos JSON/Markdown com o conteúdo do YAML, hashes,
geometria/escala, série usada, ambiente, máquina, código e origem da anotação.
Os ajustes acontecem somente na configuração; o algoritmo de US-11 não foi
alterado. `barnes events calibration-evidence <rodada.json>` acrescenta aqui
a evidência e os limiares daquela rodada, sem preencher o aceite da seção 5.

Se as combinações testadas não convergirem, apresentar o histórico ao decisor
como questão de definição operacional, registrar a resposta e revisar os
limiares/definições. Nenhuma discussão com o cliente foi enviada ou registrada
como realizada nesta implementação.

### 4.2 Convenções técnicas propostas para entrada — confirmar em C2/G3

- Área circular: raio do buraco em pixels × escala cm/px × `entrar.raio_fator`;
  fronteira inclusiva. Fator 1,0 e duração mínima de 0,2 s por decisão da equipe
  (12/11/2026, sem G3).
- Segmento contínuo: focinho válido dentro da área em quadros consecutivos;
  saída, focinho ausente ou salto de quadro interrompem a duração. Um quadro
  isolado não comprova duração positiva.
- Instante E: início do segmento que alcança a duração mínima. O momento da
  confirmação fica separado em `confirmed_at_s`. Reentradas são preservadas.
- Cada E é associado à primeira D do mesmo buraco/trial. D no mesmo quadro de E
  gera hesitação zero pela resolução amostral. D ausente/posterior gera
  inconsistência identificada; não se inventa descoberta.
- `delta_latency = t_E − t_D`, em segundos. `delta_distance` é o caminho do
  centro do corpo entre D e E, em cm. Centros ausentes tornam a distância
  indisponível, com motivo, sem soma parcial disfarçada de distância completa.
- A primeira E do alvo, resolvido para a rotação do trial, fornece
  `total_latency` e `total_distance`. Sem E no alvo, não há sucesso inventado.
- Tempos relativos ao intervalo útil; distâncias somadas entre amostras. FPS
  variável mantém a ressalva temporal da série de US-09. A qualidade de pose
  da US-10 acompanha a saída e os pontos já interpolados continuam identificados
  na série e em sua proveniência.

Estas são convenções implementadas para revisão; **não são palavras ou decisões
atribuídas ao laboratório**. Procedimento e formato D3 no
[guia de calibração e entrada](eventos-calibracao-entrada.md). Pendências por ticket
no [relatório da entrega](status-us12-us13.md).

### 4.3 Distância da US-18 contra a medida manual (SCRUM-225)

**Aceite r ≥ 0,95: pulado** — não há medida manual de distância nem fonte pública
com ela (decisão da equipe em 12/11/2026,
[`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §5.1). A lista abaixo
fica como roteiro caso uma referência apareça. Não há medida manual de
distância para nenhum trial. A ferramenta está pronta: `barnes metrics distance-validate
--manual <csv>` pareia o resultado atual de cada trial (gravado por `metrics
displacement`) com a referência. O relatório traz r, viés médio e erro relativo médio,
porque r não vê erro de escala: um valor automático 20% maior ainda dá r = 1. Sem
referência, a rodada é registrada como bloqueada. Os testes são sintéticos e não
representam aceite.

Pendências para destravar:

1. **Quem mede**: laboratório (D3) ou equipe, e quem assina o aceite (C6).
2. **Método**: ferramenta, ponto do corpo (centro do corpo, o mesmo da métrica) e de
   quantos em quantos quadros se marca a posição. Marcar a cada k quadros encurta o
   caminho em relação ao vídeo a 25 fps, então o método precisa estar no CSV.
3. **Trecho medido**: o mesmo intervalo útil registrado no trial (da soltura ao fim).
4. **Unidade**: cm com a mesma calibração da montagem, ou px convertidos por nós.
5. **Quais trials e quantos**: sugestão de ≥ 10–15, misturando buscas curtas e longas.
   Sem variação entre trials, r não diz nada.
6. **Inferência de pose real** nesses trials (modelo das US-07/08 treinado). Sobre a
   inferência simulada do roteiro, o r não vale como aceite.
7. **Formato de entrega**: CSV `trial_id,distance_cm_manual,observador,metodo,data`.

### 4.4 Estratégia da US-20 contra o observador: kappa de Cohen (US-21)

**Aceite kappa ≥ 0,70: pulado**: não há classificação de estratégia feita por um
observador humano, nem do laboratório nem pública (decisão da equipe em 12/11/2026,
[`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §5.1). O ferramental está
pronto e foi testado com rótulos sintéticos (`tests/strategy/test_agreement.py`), que
**não** valem como validação da regra. Sem rótulos, `barnes strategy agreement` grava a
rodada como bloqueada e sai com código 2.

**Medida.** Kappa de Cohen (`sklearn.metrics.cohen_kappa_score`, sem pesos) entre o
rótulo do observador e o da regra da US-20, sobre as três categorias na ordem fixa
`spatial`, `serial`, `random`. Junto com ele saem a concordância bruta e a **matriz de
confusão** (linha = observador, coluna = regra), além de sensibilidade e precisão por
categoria. Um kappa aceitável pode esconder uma categoria sistematicamente errada
(RN02). Se nenhum dos dois lados usou uma categoria, ela fica com zeros e é sinalizada.
O kappa indefinido (os dois lados usaram uma única e mesma categoria) e uma amostra com
menos de 3 pares são recusados: não viram número. O critério 0,70 é uma constante do
card (`barnes.strategy.agreement.KAPPA_THRESHOLD`), não um limiar G3, e por isso não
está em `configs/default.yaml`.

**Rótulo automático.** É o do resultado **mais recente do `strategy classify`** de cada
trial, buscado no histórico de `trial_results`. A linha atual pode ser de outro comando,
com `search_strategy` nulo. Um trial fica fora da comparação, com o motivo no relatório,
em quatro casos: nunca foi classificado, a regra não o classificou (US-20 RN01, que
nunca vira "aleatória"), a classificação ficou obsoleta porque a montagem foi
recalibrada, ou ele não existe no banco. Se os trials de uma mesma rodada tiverem sido
classificados com versões diferentes da seção `estrategia`, a rodada é recusada.

**Calibração × avaliação (RN05).** `barnes strategy split` sorteia a partição uma única
vez por anotação. O sorteio é estratificado pela estratégia do observador, usa semente
fixa (padrão 21) e reserva 30% para avaliação. A partição fica em `particao.json` com o
hash do CSV e nunca é sobrescrita; se o CSV mudar, ela é recusada. Os limiares só são
ajustados olhando rodadas de `calibracao`. O kappa final sai de uma rodada de
`avaliacao`, cujo relatório declara que aqueles trials não participaram do ajuste
(Cenário 3). Uma nova rodada de `avaliacao` com limiares diferentes dos de uma rodada de
avaliação anterior recebe **aviso de resultado otimista**: avaliar, ajustar e reavaliar
o mesmo subconjunto também é ajuste sobre ele.

**Ajuste (RN04): manual, sem otimizador.**

1. Rodar `strategy agreement --subconjunto calibracao`.
2. Se reprovar, ler a matriz de confusão e mudar a seção `estrategia` do YAML, sempre
   com a justificativa em [`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md)
   §10.
3. Reexecutar `strategy classify` em **todos** os trials anotados.
4. Rodar uma nova rodada de calibração.
5. Quando a calibração passar, rodar **uma** rodada de `avaliacao`.

Cada rodada fica em `data/validation/strategy/agreement-<uuid>/rodada.{json,md}`, com os
limiares usados e o hash do CSV e da partição. `strategy agreement-history` lista as
rodadas em ordem cronológica. A US-29 consome os `rodada.json`.

**Formato de entrega**: CSV `trial_id,estrategia_manual,observador,data`, em que
`estrategia_manual` pode ser `espacial|spatial`, `serial` ou `aleatoria|aleatória|random`.
O observador classifica sem ver a saída da regra, usando o critério da seção
"Estratégias".

## 5. Aceite

G3 exige aceite **por escrito** de quem decide as definições no laboratório.
Descobrir na semana 8 que quem respondeu não era quem decide é caro (C6).

| | |
|---|---|
| Nome | |
| Papel no laboratório | |
| Decide estas definições (C6) | ☐ sim ☐ não |
| Data do aceite | |
| Versão aceita | |

**Enquanto esta seção estiver em branco, o escopo não está congelado e os
critérios de aceite da seção 10 da definição não podem ser fixados.**

> **12/11/2026:** sem contato com o LNBio, esta seção fica em branco até o fim do
> projeto. As definições em uso foram aprovadas pela equipe
> ([`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §14) e o relatório
> declara que G3 não foi fechado.

## 6. Referenciais e rotação da plataforma (US-05)

Fixa em que referencial cada posição angular é expressa. Sem isso, comparar
trials (sequência de visitação, DTW/Fréchet da US-24, probe e palpites da
US-26) compara índices de buraco, que não significam a mesma posição física
se a plataforma girar ou a câmera mudar de lugar.

### 6.1 Pergunta B4: a plataforma é rotacionada entre trials?

| | |
|---|---|
| Resposta | **Suposição da equipe:** a plataforma não é rotacionada. Não houve resposta do LNBio ([`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §13). |
| Respondido por | _a preencher_ (não há resposta do laboratório) |
| Data | _a preencher_ |

Consequência (US-05 RN04): a rotação de todo trial é gravada como **0°**
(`barnes video load` usa `--rotation-deg 0` quando a opção é omitida — é aí que
mora a suposição), e a
conversão entre plataforma e sala vira identidade. A coluna
`trials.rotation_deg` e o caminho de código continuam existindo: se o
protocolo mudar, basta informar a rotação real de cada trial.

Ausência de valor **não** é 0°: um trial sem rotação registrada (por
exemplo, carregado antes da US-05) é recusado por toda análise longitudinal,
com o id do trial na mensagem (US-05 RN01, Cenário 3).

### 6.2 Buraco físico de referência

A câmera filma a plataforma de cima e não enxerga nenhum marco fixo da sala.
Como a plataforma não gira, os próprios buracos são fixos na sala: um deles é
escolhido como **buraco de referência** e passa a ser o buraco 0 de **toda**
montagem.

| | |
|---|---|
| Buraco de referência | Decisão da equipe (sem o laboratório): escolhido visualmente por quem monta a configuração, sempre o mesmo buraco físico, gravado como buraco 0 ([`decisoes-sem-laboratorio.md`](decisoes-sem-laboratorio.md) §1) |
| Como identificá-lo no vídeo | marcas estáveis entre sessões (desgaste, cor ou textura na borda do buraco) ou elementos fixos na borda do quadro; conferência cruzada por outra pessoa da equipe |

Se a câmera for deslocada entre dias, cria-se uma montagem nova, arrastando
de novo até o mesmo buraco físico. Os ângulos de sala continuam comparáveis
entre as montagens.

### 6.3 Os três referenciais

Todos usam a mesma convenção angular: 0° apontando para a direita da imagem
(+x) e ângulos crescendo no sentido horário na tela.

| Referencial | Sufixo nas saídas | O que é | Muda com |
|---|---|---|---|
| Imagem | `_image` | Ângulo do buraco no quadro do vídeo (`holes.angle_deg`) | Posição da câmera |
| Plataforma | `_platform` | Índice do buraco, 0 a N−1 (0 = buraco de referência) | Nada, é o próprio buraco |
| Sala | `_room` | Ângulo fixo na sala, com 0° no buraco de referência em repouso | Nada, é fixo na sala |

```
sala(k) = (k · 360/N + rotação) mod 360
```

A rotação é positiva no mesmo sentido da numeração dos buracos. O buraco-alvo
é marcado com a plataforma em repouso, então sua posição na sala é fixa.

### 6.4 Identificação nas saídas (US-05 RN05)

Toda coluna que carrega uma posição traz no nome o sufixo do referencial em
que está expressa, por exemplo `target_hole_platform` e
`target_angle_deg_room`. Uma coluna de posição sem sufixo é um erro de
exportação.

### 6.5 Orientação da cabeça θ (US-09)

A orientação da cabeça é o ângulo do vetor **centro do corpo → focinho**, no quadro do
vídeo (sufixo `_image`), com **a mesma convenção dos buracos** (§6.3, `holes.angle_deg`):

| | |
|---|---|
| Eixos | os da imagem: origem no canto superior esquerdo, **y cresce para baixo** |
| Origem do ângulo | **0° aponta para a direita da imagem (+x)** |
| Sentido | **horário na tela**: 90° = para baixo, 180° = esquerda, 270° = para cima |
| Faixa | [0, 360) |
| Fórmula | `θ = atan2(y_focinho − y_centro, x_focinho − x_centro)`, em graus, mod 360 |
| Sem θ | quando falta focinho ou centro do corpo, ou os dois coincidem: θ = NaN, `pose_valida = false` |

Consequência prática: um focinho apontando do centro da plataforma para o buraco *k*
tem θ = `holes.angle_deg` desse buraco. O ângulo cabeça→buraco da US-11 pode ser
calculado pela mesma fórmula e comparado diretamente com θ.

A conversão para cm não altera θ: a escala da US-02 é um fator único para os dois
eixos. θ fica no referencial da imagem. Para comparar orientações entre trials ou
montagens, converta para o referencial da sala (§6.3) subtraindo o ângulo de imagem do
buraco 0 e somando a rotação do trial.

Verificação (US-09 Cenário 2): em trajetórias sintéticas retas nas 8 direções, θ
coincide com a direção de deslocamento (< 1e-6° sem ruído; desvio mediano ≤ 5° com
ruído de 1 px num eixo de corpo de 20 px). É tolerância de **teste** do cálculo, não
limiar do laboratório. O contrato completo da série está em
[`contrato-trajetoria.md`](contrato-trajetoria.md).

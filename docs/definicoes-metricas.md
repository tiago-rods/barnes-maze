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

## 1. Limiares a acordar

| # | Parâmetro | Chave em `default.yaml` | Valor acordado | Origem | Status |
|---|---|---|---|---|---|
| 1 | Distância para "encontrar" | `encontrar.distancia_cm` | 3 cm (provisório) | C1 | provisório (sem G3) |
| 2 | Ângulo de orientação da cabeça | `encontrar.angulo_graus` | 30° (provisório) | C1 | provisório (sem G3) |
| 3 | Critério de "entrar" | `entrar.focinho_dentro` | — | C2 | pendente |
| 3a | Área de entrada, como fator do raio físico calibrado | `entrar.raio_fator` | — | C2 | pendente (`null`) |
| 4 | Duração mínima de entrada | `entrar.duracao_minima_s` | — | C2 | pendente |
| 5 | Duração mínima de dwell | `dwell.duracao_minima_s` | — | C2 | pendente |
| 6 | O que conta como erro | `erro.criterio` | — | C3 | pendente |
| 7 | Duração mínima do erro | `erro.duracao_minima_s` | — | C3 | pendente |
| 8 | Estratégia — cruzamentos do centro | `estrategia.cruzamentos_centro_min` | — | C4 | pendente |
| 9 | Estratégia — adjacência angular | `estrategia.adjacencia_angular_graus` | — | C4 · B2 | pendente |
| 10 | Estratégia — erros até o alvo | `estrategia.erros_ate_alvo_max` | — | C4 | pendente |
| 11 | Estratégia — entropia máxima | `estrategia.entropia_max_espacial` | — | C4 | pendente |
| 12 | Tempo limite do trial | `trial.tempo_limite_s` | — | B5 | pendente |

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
> **Confirmar com o laboratório (C3):** se revisitas contam como novos erros, se
> o limite de duração é inclusivo (≥) e se erros depois de achar o alvo entram
> no total.

### Estratégias: aleatória, serial, espacial
_A definir em G3 — é a regra que o classificador precisa reproduzir (US-20) e
contra a qual o kappa é medido (US-21). Sem ela, não há como validar._

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
> útil). Enquanto `trial.tempo_limite_s` (linha 12, B5) estiver `null`, o cálculo é
> recusado com erro: nenhum valor provisório foi posto no lugar. "Detector não
> executado" (hoje o de entrada, US-13) **não** é censura: `total_*` sai vazio, com
> aviso. Distância percorrida pelo `centro_corpo`, atravessando lacunas de pose em
> linha reta — **confirmar com o laboratório** qual ponto o `trials.csv` usa.

## 3. Protocolo de referência

| | |
|---|---|
| Artigo ou protocolo publicado a seguir (C5) | _a preencher_ |

## 4. Calibração

Registro das rodadas de ajuste contra a anotação manual (US-12, US-13).

| Rodada | Data | Parâmetro | Valor testado | Diferença vs. anotação | Resultado |
|---|---|---|---|---|---|
| | | | | | |

Alvos: encontrar ≤ 0,5 s · entrar ≤ 0,3 s.

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
  fronteira inclusiva. Fator e duração mínima permanecem `null` até definição.
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

## 6. Referenciais e rotação da plataforma (US-05)

Fixa em que referencial cada posição angular é expressa. Sem isso, comparar
trials (sequência de visitação, DTW/Fréchet da US-24, probe e palpites da
US-26) compara índices de buraco, que não significam a mesma posição física
se a plataforma girar ou a câmera mudar de lugar.

### 6.1 Pergunta B4: a plataforma é rotacionada entre trials?

| | |
|---|---|
| Resposta | **Não.** O LNBio não rotaciona a plataforma. |
| Respondido por | _a preencher_ |
| Data | _a preencher_ |

Consequência (US-05 RN04): a rotação de todo trial é gravada como **0°**,
explicitamente (`barnes video load` usa `--rotation-deg 0` por padrão), e a
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
| Buraco de referência | _a definir com o laboratório (ex.: buraco marcado com fita, ou o mais próximo da porta)_ |
| Como identificá-lo no vídeo | _a preencher_ |

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

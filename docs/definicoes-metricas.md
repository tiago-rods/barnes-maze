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
| 1 | Distância para "encontrar" | `encontrar.distancia_cm` | — | C1 | pendente |
| 2 | Ângulo de orientação da cabeça | `encontrar.angulo_graus` | — | C1 | pendente |
| 3 | Critério de "entrar" | `entrar.focinho_dentro` | — | C2 | pendente |
| 4 | Duração mínima de entrada | `entrar.duracao_minima_s` | — | C2 | pendente |
| 5 | Duração mínima de dwell | `dwell.duracao_minima_s` | — | C2 | pendente |
| 6 | O que conta como erro | `erro.criterio` | — | C3 | pendente |
| 7 | Duração mínima do erro | `erro.duracao_minima_s` | — | C3 | pendente |
| 8 | Estratégia — cruzamentos do centro | `estrategia.cruzamentos_centro_min` | — | C4 | pendente |
| 9 | Estratégia — adjacência angular | `estrategia.adjacencia_angular_graus` | — | C4 · B2 | pendente |
| 10 | Estratégia — erros até o alvo | `estrategia.erros_ate_alvo_max` | — | C4 | pendente |
| 11 | Estratégia — entropia máxima | `estrategia.entropia_max_espacial` | — | C4 | pendente |
| 12 | Tempo limite do trial | `trial.tempo_limite_s` | — | B5 | pendente |

## 2. Definições em prosa

Preencher **com as palavras do laboratório**, não com as nossas.

### Encontrar
_A definir em G3._

### Entrar / checar fisicamente
_A definir em G3._

### Erro
_A definir em G3._

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

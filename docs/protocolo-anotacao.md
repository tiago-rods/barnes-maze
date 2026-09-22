# Protocolo de anotação de pose

**US-06 · Sprint 1 · status: rascunho**

Como os quadros são amostrados, rotulados e divididos para treinar o modelo de
pose (US-07) e para medir seu erro por região (US-08).

## 1. Pontos anotados

Três pontos, animal único:

| Ponto | Definição | Observação |
|---|---|---|
| Focinho | | É o ponto que define os eventos de buraco — o mais crítico |
| Centro do corpo | | Base do eixo de orientação |
| Base da cauda | | |

A orientação da cabeça θ é derivada do eixo **centro → focinho** (US-09).

## 2. Amostragem de quadros

A amostragem cobre as três regiões, **não** quadros aleatórios: o erro do modelo
é reportado separadamente por região em US-08, e a perda de pose junto à borda —
sombra e oclusão do focinho — acontece exatamente onde os eventos ocorrem.

| Região | Quadros | Por quê |
|---|---|---|
| Centro da plataforma | _a definir_ | |
| Borda | _a definir_ | Principal causa de perda de pose |
| Proximidade dos buracos | _a definir_ | Onde os eventos acontecem |

Total-alvo: poucas centenas de quadros (animal único, três pontos).

## 3. Divisão treino / validação / teste

**Divisão por trial, nunca por quadro.** Quadros do mesmo trial são quase
idênticos entre si; dividir por quadro infla a métrica de teste.

| Conjunto | Trials | Proporção |
|---|---|---|
| Treino | | |
| Validação | | |
| Teste | | |

## 4. Ferramenta

Interface de anotação do próprio SLEAP — corta uma dependência externa.

> Sujeito à revisão de abordagem de pose do Sprint 1. Se a segmentação por
> contraste bastar, ou se YOLO-pose for adotado, este protocolo muda junto.

## 5. Privacidade

Nada sai das máquinas do grupo — nem vídeo, nem quadros rotulados. O treino é
local. Se o fallback para nuvem for acionado, sobem **apenas os quadros
rotulados**, nunca os trials, e só com resposta explícita de D4.

## 6. Registro das rodadas

| Rodada | Data | Anotador | Quadros | Versão do conjunto |
|---|---|---|---|---|
| | | | | |

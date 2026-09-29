# Manual do usuário

**US-30 · Sprint 5 · status: rascunho**

Manual de instalação e operação para o laboratório.

> **Critérios que este documento precisa fazer passar (US-30):**
> instalação concluída por **pessoa de fora** seguindo só este manual;
> operador processa um trial em **≤ 10 min**; funciona **offline**.
>
> Escrever pensando em quem nunca viu o projeto. Testar com alguém de fora
> **antes** do Sprint 5 — não durante.

## 1. Requisitos

| | |
|---|---|
| Sistema operacional | _D2_ |
| Python | 3.11 |
| GPU | Não obrigatória para inferência |
| Banco de dados | PostgreSQL — ver seção 2 |

## 2. Instalação

### 2.1 Software

_A preencher._

### 2.2 Banco de dados

> **Ponto em aberto — US-27 RN07, resolver até o Sprint 2.**
> PostgreSQL é um **servidor**, não um arquivo: exige instalação e serviço
> rodando na máquina do laboratório. Isso atinge dois critérios de aceite de
> US-30 — instalação por pessoa de fora seguindo só o manual, e operação
> offline. Definir a via: instalador embarcado, container, ou serviço já
> existente no LNBio.
>
> Se a distribuição se mostrar inviável para o perfil do operador, **SQLite é a
> alternativa adequada** ao volume real do estudo (alguns milhões de linhas).

_A preencher._

## 3. Configurar uma montagem

Uma vez por arranjo de labirinto + câmera, não por trial. A geometria é
paramétrica (centro, raio, número de buracos e ângulo inicial — sem editor
de polígonos) e fica salva no banco (tabelas `maze_configs` e `holes`), não
em arquivo.

**Ainda pendentes nesta seção — não incluídos no procedimento abaixo:**
escala px→cm (US-02) e rotação/referencial de sala (US-05). Sem eles, uma
montagem tem geometria e alvo, mas nenhuma métrica em cm.

### 3.1 Criar uma montagem

```
uv run barnes maze create \
  --experiment-id <id> --name "<nome da montagem>" \
  --reference-frame <video ou imagem de referência> \
  --arena-diameter-cm <cm> --hole-diameter-cm <cm>
```

Por padrão abre uma janela OpenCV sobre o quadro de referência, ajustável
**com o mouse e o teclado**, sem precisar informar centro/raio/N/ângulo/alvo
na linha de comando (eles têm um valor inicial razoável e são corrigidos na
janela):

- **Tecla `a`** detecta automaticamente o centro e o raio da plataforma no
  quadro (maior região clara contígua) e já reposiciona a marca amarela de
  centro — usar antes de arrastar poupa a parte mais difícil de "achar o
  meio a olho".
- **Arraste o botão esquerdo** do centro (o detectado por `a`, ou qualquer
  ponto) até um buraco real visível — isso (re)define centro, raio **e**
  ângulo inicial de uma vez, calibrados contra um buraco de verdade (o
  ângulo vem da direção do arraste).
- **Clique com o botão direito** perto de um buraco já desenhado para
  marcá-lo como o buraco-alvo (fica vermelho).
- **`+` / `-`** aumentam/diminuem N (número de buracos) ao vivo, com teto de
  **30** (`+` não passa disso).
- **`Enter`, `q` ou `Esc`** confirma e fecha a janela, salvando a última
  geometria válida mostrada.

A marca amarela em cruz mostra onde está o centro atual, para conferir
visualmente se bate com o centro real da plataforma antes de confirmar.

As instruções também aparecem no rodapé da própria janela. Repita o arraste
quantas vezes quiser até os buracos desenhados coincidirem com os buracos
reais (Cenário 1) — cada novo arraste substitui centro/raio/ângulo
anteriores.

Se quiser informar os parâmetros manualmente em vez de usar o mouse (por
exemplo, reproduzindo uma montagem já medida), as opções `--center-x`,
`--center-y`, `--platform-radius-px`, `--hole-count`, `--start-angle-deg`,
`--target-hole-number` e `--hole-radius-px` continuam aceitas e só definem
o ponto de partida — a janela interativa ainda abre por cima. Use
`--no-interactive` para pular a janela e persistir direto os valores
informados (útil em script/teste); nesse caso `--center-x`, `--center-y` e
`--platform-radius-px` passam a ser obrigatórios.

Se algum parâmetro for inválido (N ≤ 2, raio não positivo, ou índice de
alvo fora de `0..N-1`), o comando recusa a gravação e informa qual
parâmetro falhou (com `--no-interactive`) ou simplesmente não atualiza o
desenho até um arraste válido ser feito (no modo interativo).

### 3.2 Reaproveitar uma montagem existente

```
uv run barnes maze show <id-da-montagem>
```

Lê a montagem do banco e imprime centro, raio, buracos e alvo — sem abrir
nenhuma janela. É o mesmo dado que outros comandos do pipeline vão
consultar para reaplicar a montagem a um novo trial, sem repetir a
configuração interativa.

## 4. Processar um trial

_A preencher. Este é o procedimento cronometrado no critério de ≤ 10 min._

## 5. Saídas

| Arquivo | Conteúdo |
|---|---|
| CSV por trial | métricas do trial |
| CSV consolidado | todos os trials |
| `trials.csv` / `probes.csv` | formato que o `barnes_maze.py` do laboratório lê sem alteração (US-25) |
| Curvas e trajetória desenhada | |

## 6. Problemas comuns

_A preencher conforme aparecerem — especialmente o aviso de fps variável
(US-01), que não é corrigido pelo software e fica com o usuário._

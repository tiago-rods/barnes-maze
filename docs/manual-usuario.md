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
  --center-x <px> --center-y <px> --platform-radius-px <px> \
  --hole-count <N> --start-angle-deg <graus> --target-hole-number <0..N-1> \
  --hole-radius-px <px> --arena-diameter-cm <cm> --hole-diameter-cm <cm>
```

Por padrão abre uma janela OpenCV com barras de ajuste (trackbars) para
centro, raio, N, ângulo inicial e índice do alvo, desenhando os buracos
sobre o quadro de referência em tempo real — ajuste até os buracos
desenhados coincidirem com os buracos reais e confirme com `Enter`, `q` ou
`Esc`. Use `--no-interactive` para pular a janela e persistir direto os
valores informados (útil em script/teste).

Se algum parâmetro for inválido (N ≤ 2, raio não positivo, ou índice de
alvo fora de `0..N-1`), o comando recusa a gravação e informa qual
parâmetro falhou antes de abrir qualquer janela.

**Limitação conhecida:** a barra do índice do alvo tem o limite máximo
fixado no valor de N no momento em que a janela abre — se você aumentar N
pela barra, não é possível mover a barra do alvo além do limite antigo
nesta versão. Se precisar de um alvo em índice alto com N maior, informe um
`--hole-count` já correto antes de abrir a janela.

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

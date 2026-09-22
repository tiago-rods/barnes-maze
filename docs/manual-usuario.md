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

Uma vez por arranjo de labirinto + câmera, não por trial.

_A preencher — US-02, US-04, US-05._

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

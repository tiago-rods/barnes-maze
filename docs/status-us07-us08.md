# Entrega US-07 e US-08 — 7 de outubro de 2026

**Implementação de software concluída e testada nas condições disponíveis.**
Os cards ainda não cumprem integralmente a definição de pronto operacional:
faltam dados anotados reais, treino na NVIDIA e validação do modelo na máquina
do laboratório. Não foi criado um modelo científico fictício para preencher
essas pendências.

## Entrega por subtarefa

| Ticket | Implementado | Situação do aceite real |
| --- | --- | --- |
| SCRUM-100 | `pose hardware`: consulta nvidia-smi, VRAM, RAM, driver e registra máquina/ambiente. | Esta máquina foi inspecionada: Intel Iris Xe, aproximadamente 16 GB de RAM, sem NVIDIA/nvidia-smi. Faltam relatórios das demais máquinas do grupo e escolha efetiva. |
| SCRUM-101 | SLEAP-NN 0.3.1, sleap-io 0.9.2, PyTorch 2.7.1 e torchvision 0.22.1 fixados; build cu128 definido para Windows/Linux. | API real validada em CPU. Compatibilidade do driver e execução CUDA precisam ser confirmadas na NVIDIA escolhida; o worker faz essa checagem. |
| SCRUM-102 | `pose prepare-training`: pacote portátil dos PNGs rotulados e três subconjuntos SLP, hashes e versão por conteúdo. | Exportação SLP real testada. Pacote científico aguarda anotações, divisão e PNGs reais da US-06, ausentes neste workspace. |
| SCRUM-103 | `pose train`: treino real SLEAP por montagem, GPU obrigatória, perfil YAML, seed, validação separada, logs, falhas preservadas. | Um ensaio sintético de uma época em CPU confirmou integração. O modelo real não foi treinado: faltam dados e NVIDIA. |
| SCRUM-104 | Identificador único por tentativa, pesos/configuração verificados por hash em `models/`, tabela `execucao` e registro recuperável/idempotente. | Pesos reais serão gerados no treino. A migração não foi aplicada em banco do laboratório; PostgreSQL não está disponível neste ambiente. |
| SCRUM-105 | Manifestos de dados/modelo, parâmetros resolvidos, dependências, host, RAM/GPU/driver, tempo, commit e cópia do código. | Mecanismo testado; registro científico surge com a execução real. |
| SCRUM-106 | `pose plan-training`: grupo → instituição → Kaggle → Colab, pendência explícita quando disponibilidade desconhecida e D4 obrigatório para nuvem. `--defer-db` evita expor o banco em máquina remota. | Nenhuma máquina/conta externa foi provisionada ou acionada. Faltam inventário completo, disponibilidade efetiva e, se necessário, D4. Nenhum upload realizado. |
| SCRUM-108 | `pose evaluate`: erro euclidiano mediano global e por ponto, normalizado pelo corpo anotado, limiar estrito <0,5. | Critério coberto por testes; erro científico depende de modelo e teste reais. |
| SCRUM-109 | Relatórios JSON/Markdown por centro, borda e proximidade de buraco, usando centro anotado e geometria da montagem. | Relatórios sintéticos validados; relatório real permanece pendente. |
| SCRUM-110 | `pose infer`: pesos e vídeo locais, CPU/GPU, telemetria desativada e proteção Python de rede externa. | Backend real executado sob proteção offline em ensaio sintético. Não atesta máquina do laboratório fisicamente desconectada. |
| SCRUM-111 | Tempo por trial em `execucao.json` e PostgreSQL; identidade do vídeo, montagem e intervalo úteis conferidos. | Medição validada com vídeo sintético; benchmark de trials reais no laboratório pendente. |
| SCRUM-112 | Reprovação da borda gera `us06-borda.json`/`.md`, com pedido de novos trials e proteção do conjunto de teste. | Geração local testada. Nenhum ticket externo foi aberto e nenhuma nova rodada humana foi executada. |

## Verificações executadas

- Suíte principal: **481 testes passaram; 60 foram pulados; nenhuma falha**.
- Dos 60 pulados, 57 exigem PostgreSQL configurado, 2 exigem SLEAP-NN no
  ambiente principal e 1 exige AF_UNIX disponível.
- Em `.venv-pose-check`, ambiente isolado com SLEAP-NN real e PyTorch CPU:
  **19 testes passaram**, incluindo configuração nativa, uma época de treino
  sintético, geração de `best.ckpt`, carregamento e predição real. Esse número
  inclui testes também presentes na suíte principal; não representa 19 testes
  únicos adicionais. O backend emitiu avisos de desempenho/depreciação e métricas
  vazias no pequeno conjunto sintético, sem reprovar o teste de integração.
- Exportação e transporte de pacotes `sleap-io` reais validados.
- Ruff sem erros; `git diff --check` sem erros de whitespace;
  `uv lock --check --offline` confirma consistência do lockfile.
- CLI testada: ajuda, opções, bloqueio de GPU, prioridade/D4, preparo, treino,
  avaliação reprovada, registro de falhas e recuperação após queda do banco.
- Inferência testada com vídeo sintético: leitura sequencial sem seek, hash,
  resolução, montagem, limites fracionários e intervalo até o fim do vídeo.

O ambiente principal recebeu `uv` e dependências do extra `anotacao`, sincronizadas
com o lockfile. O ambiente separado `.venv-pose-check/` contém dependências CPU
para ensaios e é ignorado pelo Git. Pesos temporários de teste não são modelos
do laboratório e não substituem os artefatos esperados em `models/`.

## Onde estão as mudanças

- `src/barnes/pose/`: dados, hardware/fallback, treino, avaliação, inferência e proteção offline.
- `src/barnes/cli_pose.py` e integração em `cli.py`: comandos US-07/US-08.
- `database/migrations/0006_pose_executions.sql` e `db/pose_executions.py`: auditoria PostgreSQL.
- `configs/pose/single_animal.yaml`: parâmetros iniciais de treino.
- `pyproject.toml`/`uv.lock`: versões e origem do build PyTorch.
- `tests/pose/` e `tests/db/test_pose_executions.py`: cenários e integração.
- README, manual, DER, revisão dos cards e roteiro de demonstração atualizados.

## Pendências para marcar ambos os cards como prontos

1. Disponibilizar anotações/PNGs/divisão reais da US-06 e a montagem cadastrada.
2. Escolher uma máquina NVIDIA elegível; se nenhuma do grupo atender, usar
   a GPU institucional confirmando acesso, driver e disponibilidade.
3. Disponibilizar PostgreSQL de teste, aplicar a migração `0006` e executar
   os testes de banco. A instalação existente do laboratório não foi alterada.
4. Rodar o treino real, registrar o modelo e avaliar o teste por região;
   se reprovar, realizar a rodada de anotação indicada e repetir.
5. Executar inferência de trial real na máquina do laboratório efetivamente
   sem rede e guardar evidências/duração. O bloqueio Python não substitui essa prova.
6. Se nuvem for necessária, obter D4 favorável e realizar apenas a transferência
   autorizada dos quadros rotulados. O software prepara e controla o plano;
   provisionamento e upload não são automáticos.

Procedimentos e comandos completos: [guia de treino e avaliação](pose-treino-avaliacao.md).

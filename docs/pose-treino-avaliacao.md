# US-07 e US-08 — treino, avaliação e inferência de pose

O projeto usa **SLEAP-NN 0.3.1**, backend PyTorch do SLEAP, para um animal
e os pontos `focinho`, `centro_corpo` e `base_cauda`. A GUI de anotação é uma
instalação separada. A implementação fornece os comandos abaixo; concluir os
cards exige executar o treino com anotações reais e validar o modelo no laboratório.

## Ambiente adotado

| Componente | Versão |
| --- | --- |
| Python | 3.11 (restrição do projeto) |
| SLEAP-NN | 0.3.1 |
| sleap-io | 0.9.2 |
| PyTorch | 2.7.1 |
| torchvision | 0.22.1 |
| Build NVIDIA em Windows/Linux | CUDA 12.8 (`cu128`) |

As versões diretas estão em `pyproject.toml`; `uv.lock` fixa também as
dependências transitivas. SLEAP 1.5+ usa PyTorch; não montar um ambiente
TensorFlow antigo para estes comandos. Fontes: [instalação SLEAP](https://docs.sleap.ai/latest/installation/),
[dependências do SLEAP-NN 0.3.1](https://github.com/talmolab/sleap-nn/blob/v0.3.1/pyproject.toml)
e [pares PyTorch/torchvision e CUDA](https://pytorch.org/get-started/previous-versions/).

Antes de instalar o extra pesado, executar em **cada máquina oferecida**:

```powershell
uv sync --locked
nvidia-smi
uv run --no-sync barnes pose hardware --out data/pose/hardware-integrante1.json
```

O diagnóstico grava modelo/índice da GPU, VRAM, driver, RAM, host, sistema e
versões instaladas. Sai com código 1 quando não confirma os requisitos.
Exige uma GPU NVIDIA com pelo menos 4096 MiB; não soma VRAM de GPUs diferentes.
RAM mínima: 16.000.000.000 bytes utilizáveis pelo SO (16 GB decimal), evitando
rejeitar 16 GiB nominais por memória reservada. `eligible` comprova RAM/VRAM;
o worker verifica CUDA e executa um pequeno cálculo real na GPU antes do treino.
Um driver que não consiga executar esse build causa falha registrada.

Na máquina NVIDIA escolhida, com rede apenas para instalar as dependências:

```powershell
uv sync --locked --extra pose
uv run --no-sync python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
uv run --no-sync sleap-nn system
```

Os wheels fornecem o runtime CUDA; o driver NVIDIA é necessário no sistema.
Não é preciso instalar o CUDA Toolkit para usar os wheels. Se a GPU/driver
não aceitar CUDA 12.8, revisar e versionar outro ambiente compatível, sem
trocar dependências silenciosamente. Não instalar o extra de treino em uma
máquina sem NVIDIA apenas para executar os testes comuns.

## Escolha da máquina e D4

Reunir os relatórios de todas as máquinas oferecidas. Se nenhuma atender,
a primeira alternativa é a GPU institucional. Disponibilidade desconhecida
não conta como indisponível. O plano registra as evidências usadas e nunca
envia arquivos:

```powershell
uv run --no-sync barnes pose plan-training --report data/pose/hardware-integrante1.json --report data/pose/hardware-integrante2.json --institutional sim --out data/pose/plano-treino.json
```

Somente se instituição estiver indisponível, declarar `--institutional nao`
e a disponibilidade de Kaggle/Colab. Nuvem exige `--d4-reference` com a
referência da resposta **explicitamente favorável**, não uma pergunta pendente:

```powershell
uv run --no-sync barnes pose plan-training --report data/pose/hardware-integrante1.json --institutional nao --kaggle sim --d4-reference "Referência da autorização favorável do laboratório" --out data/pose/plano-nuvem.json
```

Kaggle vem antes de Colab. Para escolher Colab, Kaggle precisa estar
explicitamente indisponível. A máquina de destino ainda precisa passar pelo
diagnóstico e pela verificação CUDA. O sistema não provisiona contas nem faz
upload automático. Uma transferência para nuvem, quando autorizada, leva só
o pacote preparado de PNGs rotulados, rótulos e divisão; nunca `data/raw/`,
vídeos originais, credenciais ou uma cópia inteira da pasta de trabalho.

## Preparar dados reais da US-06

Pré-requisitos: anotações completas, pelo menos um trial em cada subconjunto,
PNGs da amostragem e `amostragem.csv` com a montagem correta. Cada pacote e
modelo pertence a **uma montagem**. Preparar arquivos US-06 separados por
montagem quando houver mais de uma; não misturar câmeras/configurações.

```powershell
uv sync --locked --extra anotacao
uv run --no-sync barnes pose prepare-training --maze-config-id 1 --annotations data/annotations/anotacoes.csv --manifest data/annotations/divisao.csv --samples data/annotations
```

Saída: `data/pose/datasets/dataset-<sha256>/`. O comando mostra o caminho
completo. O pacote contém `treino.pkg.slp`, `validacao.pkg.slp`, `teste.pkg.slp`,
os PNGs, CSVs congelados e `manifest.json` com hashes. Os SLPs têm imagens
embutidas para permitir transporte; são saída de treino, não entrada do
`import-slp` da US-06, que continua recusando projetos sem identidade recuperável.

São rejeitados: pontos faltando/fora da imagem, PNGs inválidos, divisão
incompleta, duplicatas, trials em mais de um subconjunto, PNGs idênticos entre
subconjuntos e montagem divergente. O mesmo conteúdo reutiliza a mesma versão,
depois de conferir integridade. Falhas de preparação são preservadas; corrigir
a origem e usar outro diretório `--out` se a versão incompleta já existir.

## Treinar uma vez por montagem

Configurar o PostgreSQL **local** e aplicar as migrações, incluindo `0006`:

```powershell
$env:BARNES_DATABASE_URL = "postgresql://barnes:barnes@localhost:5432/barnes"
uv run --no-sync barnes db migrate
```

Na máquina escolhida, ativar o extra `pose` e usar o caminho mostrado na preparação:

```powershell
uv sync --locked --extra pose
$dataset = "data/pose/datasets/dataset-<identificador-real>"
uv run --no-sync barnes pose train --dataset $dataset --config configs/pose/single_animal.yaml
# Se for a GPU institucional:
uv run --no-sync barnes pose train --dataset $dataset --location institucional --plan data/pose/plano-treino.json
```

Escolher **um** dos comandos de treino conforme o local; não executar ambos
como uma sequência. O plano é obrigatório para fallback, e o comando refaz
as regras de prioridade/D4 antes de iniciar. Treino não recebe `--trial`.
Trials da mesma montagem reutilizam o modelo; novas rodadas geram novos IDs.

Se a máquina institucional/nuvem não tem acesso ao banco local do laboratório,
acrescentar `--defer-db`. O treino registra tudo nos arquivos e deixa explícito
que o registro em `execucao` está pendente. Ao trazer o diretório do modelo de
volta, executar `pose register-run <diretorio> --kind treino` no laboratório.
Essa opção não pula diagnóstico de GPU, verificação de dados ou regras D4;
permite executar sem copiar credenciais ou expor o PostgreSQL à nuvem.

O perfil inicial usa UNet, seed 42, 100 épocas máximas, batch 2, escala 0,5,
Adam com taxa 0,0001 e parada antecipada pela validação. São parâmetros
iniciais da equipe, não uma promessa de qualidade ou de caber em qualquer
vídeo de alta resolução com 4 GiB. Ajustes são feitos no YAML e ficam no
registro. Treino vê apenas treino e validação; teste não entra na otimização.

Cada tentativa cria `models/sleap-maze-<montagem>-<uuid>/`, ignorada pelo Git:

- `manifest.json`: ID, estado, dados, hiperparâmetros, ambiente, máquina, tempos e hashes;
- `parameters.yaml`, `config.yaml`, `resolved_config.yaml`: parâmetros fornecidos e resolvidos;
- `training.log` e diagnóstico de runtime: execução e eventuais falhas;
- `sleap/best.ckpt` e `sleap/training_config.yaml`: modelo carregável;
- `dataset_manifest.json` e `source/`: versão dos dados, código e dependências usados.

Um erro ou interrupção não vira modelo concluído. Inferência recusa tentativas
incompletas e artefatos alterados. Seeds e operações determinísticas ajudam a
reprodução; hardware, drivers e bibliotecas diferentes podem produzir diferenças
numéricas. Preservar também o pacote de dados e os arquivos do ambiente.
Fazer backup local de `models/` e dos pacotes: estar fora do Git não é backup.

## Avaliar o modelo — US-08

Na máquina de treino ou do laboratório, com dependências e pesos locais:

```powershell
$model = "models/sleap-maze-1-<identificador-real>"
uv run --no-sync barnes pose evaluate --model $model --dataset $dataset --device cpu
# GPU, se disponível: --device cuda:0
```

O backend recebe exclusivamente pixels dos PNGs de teste. O comando exige o
mesmo pacote congelado do treino, verifica hashes e usa a geometria da montagem
registrada no banco. A região vem do `centro_corpo` **anotado**, não do predito.
São reutilizadas as fronteiras do protocolo US-06, registradas no relatório;
a proximidade de buraco tem prioridade sobre borda/centro.

Definição operacional de corpo: distância euclidiana entre focinho e base da
cauda anotados em cada quadro. O erro euclidiano de cada ponto é dividido por
esse comprimento **antes** de calcular a mediana. Comprimento zero é inválido.
Essa convenção fica explícita para revisão da equipe/laboratório; não usa
escala em centímetros nem limiares de métricas comportamentais de G3.

`avaliacao.json` e `avaliacao.md` mostram mediana em pixels e fração de corpo,
por ponto e agregada, globalmente e em centro/borda/buraco. O aceite é estrito
`< 0,5` para cada ponto e para o agregado, global e em cada região. Regiões
sem amostras e predições ausentes/não finitas impedem aceite; não são descartadas
para melhorar a mediana. Essa política de cobertura é deliberadamente conservadora.

Se a borda reprovar, a avaliação sai com código 1 e cria `us06-borda.json`/`.md`
solicitando nova anotação em **novos trials**, com foco na borda. Trials de teste
continuam congelados, sem migrar para treino. É uma tarefa local rastreável;
nenhum ticket externo é criado automaticamente.

## Inferência por trial e validação sem rede

Antes de desconectar a máquina do laboratório, instalar todas as dependências,
copiar por meio autorizado o modelo e disponibilizar o PostgreSQL local. Em
seguida, desconectar a rede conforme o procedimento do laboratório e executar:

```powershell
uv run --no-sync barnes pose infer --model $model --trial 1 --device cpu
uv run --no-sync barnes pose executions --trial 1
```

`--no-sync` evita que o gerenciador tente resolver/baixar pacotes enquanto
offline. Alternativa: `.venv\Scripts\barnes.exe pose infer ...`.
O vídeo vem do cadastro; se foi movido, usar `--video caminho/local.mp4`.
O hash precisa coincidir. Montagem, resolução, FPS e intervalo útil vêm do
trial; não há opção para trocar silenciosamente a montagem. Leitura sequencial
desde o começo evita erros de seek; o modelo processa somente o intervalo útil.

Cada execução gera `data/pose/inference/inferencia-<uuid>/pose.csv` e
`execucao.json`. O CSV contém índice original, tempo desde o início do vídeo,
coordenadas em pixels `_image` e confiança dos três pontos. Pontos ausentes
permanecem ausentes; correção/interpolação e orientação são das próximas histórias.
O tempo registrado cobre carregamento, verificações do vídeo, decodificação,
inferência e escrita; não inclui a transação posterior do PostgreSQL.

Treino/inferência desativam telemetria e bloqueiam conexões externas pela API
Python de sockets, preservando loopback para processamento local. Esse bloqueio
**não é firewall nem prova de desconexão física**: chamadas nativas podem não
passar por Python. O campo `physical_network_disconnection_verified` permanece
`false` na automação. Para concluir o cenário real, anexar ao aceite do card:
ID do modelo/trial/execução, identificação da máquina, procedimento de
desconexão, operador/data, duração e arquivos gerados. Não basta passar nos testes.

## Banco e recuperação

`execucao` registra treino, avaliação e inferência em linhas imutáveis. Há
modelo, montagem, trial quando aplicável, estado, duração, artefato e manifesto
JSON completo. Uma chave composta impede associar um trial à montagem errada.
`trial_results` mantém sua semântica anterior e não é sobrescrita por pose.

```powershell
uv run --no-sync barnes pose executions --model-id sleap-maze-1-<identificador-real>
```

Os comandos verificam banco/cadastro antes de iniciar processamento caro.
Se o banco cair depois, os artefatos ficam preservados. Após recuperar o banco:

```powershell
uv run --no-sync barnes pose register-run "models/sleap-maze-1-<id>" --kind treino
uv run --no-sync barnes pose register-run "data/pose/evaluations/teste-<id>" --kind avaliacao
uv run --no-sync barnes pose register-run "data/pose/inference/inferencia-<id>" --kind inferencia
```

Registrar novamente a mesma execução é idempotente; proveniência divergente
para o mesmo ID é recusada. Tentativas falhas também podem ser registradas.

## O que ainda exige execução real

Sem PNGs/rótulos e divisão reais, não há modelo científico treinado nem erro
real para reportar. Sem uma máquina NVIDIA elegível, o treino não inicia. Sem
acesso à máquina do laboratório, a validação física offline não pode ser atestada.
Inventariar esta máquina não equivale a inventariar as dos outros integrantes.
O planejamento institucional/nuvem depende de disponibilidades reais e de D4.

Os testes usam dados sintéticos e backends controlados onde necessário. Um
ensaio opcional com backend SLEAP real em CPU valida a integração de software;
ele não substitui treino NVIDIA com dados reais nem comprova qualidade do card.

```powershell
uv run --no-sync pytest
uv run --no-sync ruff check src/ tests/
```

Testes de PostgreSQL são pulados quando `BARNES_DATABASE_URL` não está configurada.
Use um banco de **teste** com migrações aplicadas para habilitá-los; não apontar
a suíte para o banco de produção. O teste nativo SLEAP depende do extra `pose`.

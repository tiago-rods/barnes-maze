"""Gera docs/roteiro-demonstracao.html a partir de docs/ROTEIRO-DEMONSTRACAO.md.

Uso, da raiz do repositório:
    uv run python scripts/gerar_roteiro_html.py

Cada bloco ```powershell do roteiro precisa de uma explicação em SECOES; a contagem
é conferida por seção (o script falha se não bater), para o guia nunca ficar
defasado em silêncio. O visual fica em scripts/guia_template.html.
"""

# ruff: noqa: C408, PIE810 -- a tabela SECOES usa dict(...) por legibilidade

from __future__ import annotations

import html
import math
import re
from pathlib import Path

# (explicação, esperado|None, interativo)
I = True

SECOES: dict[str, dict] = {
    "A.1": dict(
        titulo="Ambiente",
        sobre="Deixa a máquina pronta: código na versão que será mostrada, banco de dados rodando e bibliotecas instaladas.",
        cmds=[
            ("Entra na pasta do projeto. Todos os comandos seguintes assumem que o terminal está nela.", None),
            ("Lista arquivos alterados e não commitados. Cada execução grava o commit e se o repositório estava “sujo” (US-27); com alterações pendentes, tudo sai como não reproduzível.", "nenhuma linha"),
            ("Sobe o PostgreSQL 16 num contêiner Docker, em segundo plano. É ali que ficam experimentos, trials, montagens, eventos, métricas e execuções.", None),
            ("Instala as dependências Python exatas do `uv.lock`. O extra `anotacao` traz o leitor de projetos do SLEAP (US-06); `--system-certs` usa os certificados do Windows e evita erro de TLS.", None),
        ],
    ),
    "A.2": dict(
        titulo="Banco de demonstração limpo",
        sobre="Cria um banco só para a demonstração (`barnes_demo`), separado do banco de desenvolvimento, e apaga arquivos de ensaios anteriores. Assim o roteiro pode ser repetido do zero quantas vezes for preciso.",
        cmds=[
            ("Apaga o banco de demonstração anterior, se existir. `docker exec` roda o `psql` (cliente do Postgres) dentro do contêiner.", None),
            ("Cria o banco vazio `barnes_demo`.", None),
            ("Diz a todos os comandos `barnes` qual banco usar, só neste terminal. A porta tem de ser a que o Docker publica (`BARNES_PG_PORT` no `.env`; 5433 se não estiver definida).", None),
            ("Cria as tabelas aplicando, em ordem, os arquivos `database/migrations/*.sql`. Cada migração aplicada fica registrada, então rodar de novo não repete nada.", "migrações 0001 até 0010_us18_deslocamento.sql"),
            ("Aplica as mesmas migrações no banco de testes (`barnes_test`), usado pelo pytest. Sem isso, os testes de banco são pulados na B.1.", None),
            ("Indica ao pytest qual é o banco de testes. Os testes nunca tocam no banco de desenvolvimento nem no de demonstração.", None),
            ("Apaga as pastas geradas em ensaios anteriores (quadros de anotação, relatórios de pose, séries, eventos, validação). Vários comandos se recusam a sobrescrever arquivos existentes, de propósito.", None),
        ],
    ),
    "A.3": dict(
        titulo="Arquivos usados na demonstração",
        sobre="Define atalhos para os vídeos e as pastas, e cria arquivos de apoio: um vídeo sintético, um arquivo corrompido e uma trajetória de exemplo.",
        cmds=[
            ("Guarda o caminho do primeiro vídeo real na variável `$v1`. Daqui em diante, `$v1` substitui o caminho.", None),
            ("Segundo vídeo real, usado como trial de outro dia.", None),
            ("Vídeo completo de um trial do LNBio (6 min, 640×480): com a caixa de partida, a busca e a entrada no buraco de fuga. É o trial usado da B.9 em diante.", None),
            ("Gera `sintetico_soltura.mp4`: 10 quadros parados e depois um objeto em movimento. Serve para mostrar a detecção automática da soltura (US-03). O gerador é importado pelo caminho da pasta porque o `sleap-io` instala um pacote chamado `tests` que encobriria o do projeto.", None),
            ("Atalho para o vídeo sintético.", None),
            ("Cria um `.mp4` que na verdade é texto, para mostrar o tratamento de arquivo ilegível (US-01).", None),
            ("Cria uma trajetória mínima, em pixels, com três pontos (0, 2 e 4 s). É a entrada do `metrics process` da US-02, que lê CSV em vez da série de pose.", None),
            ("Pasta dos quadros exportados para anotação (US-06).", None),
            ("Pasta dos relatórios de máquina, planos de treino e pose simulada (Sprint 2).", None),
            ("Pasta das séries de pose da demonstração, separada da `data\\interim` de desenvolvimento.", None),
        ],
    ),
    "A.4": dict(
        titulo="Medidas físicas do labirinto",
        sobre="Medidas do aparato, usadas para converter pixels em centímetros. Sem acesso ao labirinto real, são valores típicos de um Barnes para camundongos (decisão da equipe, §12). Diga isso ao cliente.",
        cmds=[
            ("Diâmetro da plataforma, em cm. Entra na montagem e na calibração da escala.", None),
            ("Diâmetro de cada buraco, em cm.", None),
        ],
    ),
    "A.5": dict(
        titulo="Ensaio",
        sobre="Rode a Parte B inteira uma vez antes da reunião e depois refaça a A.2, para começar com o banco limpo.",
        cmds=[],
    ),
    "B.1": dict(
        titulo="Qualidade: testes automáticos e lint",
        sobre="Abre a demonstração mostrando que o código é verificado automaticamente. Os casos impossíveis de reproduzir ao vivo (fps variável, treino do modelo, etc.) estão nesses testes.",
        cmds=[
            ("Roda a suíte inteira de testes (mais de mil). Cada regra de negócio dos cards tem teste.", "nenhuma falha e 3 pulados: 2 exigem o SLEAP-NN, 1 exige AF_UNIX, que o Windows não tem"),
            ("Verificação estática do código: estilo e erros comuns.", "All checks passed!"),
        ],
    ),
    "B.2": dict(
        titulo="Cadastro do experimento",
        sobre="Cria o usuário, o experimento e o animal. Ainda não existe comando para isso, então é feito direto no banco, com SQL.",
        cmds=[
            ("Insere um usuário e guarda o id gerado em `$user`. As opções `-q -t -A` fazem o `psql` devolver só o número, e `.Trim()` tira espaços.", None),
            ("Cria o experimento desse usuário e guarda o id em `$exp`.", None),
            ("Cadastra o animal (1 experimento = 1 animal). Ele aparece no catálogo da B.14.", None),
            ("Só imprime os ids, para conferir que as variáveis foram preenchidas.", None),
        ],
    ),
    "B.3": dict(
        titulo="Montagem paramétrica do labirinto",
        sobre="A montagem é a geometria do labirinto vista pela câmera: centro, raio, número de buracos, posição e tamanho de cada buraco e qual é o alvo. Todo evento por buraco depende dela. Fica salva no banco e é reaproveitada por todos os trials gravados com a mesma câmera.",
        cmds=[
            ("Abre uma janela com um quadro do vídeo para marcar a geometria: `a` detecta a borda, `h` detecta os buracos, arrastar do centro ao buraco de referência (vira o buraco 0), botão direito no alvo, `+`/`-` muda N, `[`/`]` ajusta o raio do buraco, `Enter` confirma. `Esc` e `q` também salvam.", "montagem gravada e quantos buracos foram ajustados automaticamente", I),
            ("Busca o id da montagem mais recente com esse nome e guarda em `$maze`.", None),
            ("Confere que veio um único número. Com vários, os comandos seguintes quebram.", None),
            ("Mostra a montagem salva sem abrir janela: centro, raio, N, alvo e o ângulo de cada buraco na imagem e na sala. Prova que a configuração é reaproveitável (Cenário 2).", "(REF) no buraco 0 e (ALVO) no alvo"),
            ("Montagem própria para a câmera do vídeo completo (640×480). Use o buraco escuro de cima à direita como referência e marque o mesmo buraco como alvo; a tecla `h` acha o anel dos buracos.", "montagem gravada", I),
            ("Guarda o id dessa montagem em `$mazec`.", None),
            ("Tenta criar uma montagem com só 2 buracos, sem janela (`--no-interactive`).", "recusa dizendo qual parâmetro está errado"),
            ("Raio da plataforma negativo.", "recusa"),
            ("Buraco-alvo fora de 0..N−1.", "recusa"),
            ("Testes da geração dos buracos e das validações.", None),
        ],
    ),
    "B.4": dict(
        titulo="Carga do vídeo e leitura dos metadados",
        sobre="Primeira etapa do pipeline: ler o arquivo e extrair resolução, número de quadros, fps medido e o hash do conteúdo. O hash identifica o trial pelo conteúdo, não pelo nome do arquivo.",
        cmds=[
            ("Lê o vídeo e mostra os metadados. Abre uma janela com o primeiro quadro (`n` avança, `p` volta, `q` fecha). Sem `--experiment-id` e `--maze-config-id`, não grava nada.", "resolução, quadros, duração, fps declarado e real, sha256", I),
            ("Metadados do vídeo completo, sem janela. Ele tem o padrão de B-frames do LNBio (~32/48 ms) e era marcado como fps variável por engano até a correção de 12/11/2026.", "640x480, 9444 quadros, 377.71s, fps 25.001, sem aviso de fps variável"),
            ("Não há vídeo com fps variável no acervo; o teste cobre o caso, inclusive com o padrão real de quadros do LNBio (B-frames).", None),
            ("Arquivo que não existe.", "mensagem com o arquivo e a causa"),
            ("Formato não suportado: só `.mp4` nesta versão.", "recusa"),
            ("Arquivo corrompido.", "recusa sem traceback"),
            ("Confere que nenhuma tentativa falha criou registro parcial.", "0"),
        ],
    ),
    "B.5": dict(
        titulo="Calibração da escala px→cm",
        sobre="Quantos centímetros vale um pixel. Sem escala, nenhuma métrica em cm é calculada. A escala é salva na montagem e vale para todos os trials daquela câmera.",
        cmds=[
            ("Janela para clicar nas pontas de dois diâmetros da plataforma (4 cliques) e `Enter`. Com o tamanho real (`$arena_cm`), calcula o fator cm/px.", "fator cm/px salvo na montagem", I),
            ("Mede um terceiro diâmetro com a escala salva e compara com o tamanho real.", "erro abaixo de 3%", I),
            ("Mostra a escala, a data da calibração e o erro medido.", None),
            ("Calibra a montagem do vídeo completo com os mesmos 4 cliques.", "cerca de 0,197 cm/px", I),
            ("Teste com uma imagem sintética de escala conhecida.", None),
        ],
    ),
    "B.6": dict(
        titulo="Recorte do intervalo útil do trial",
        sobre="O intervalo útil é o trecho do vídeo que conta como trial: da soltura do animal até o fim. Tudo fora dele é ignorado, e o tempo zero passa a ser a soltura.",
        cmds=[
            ("Detecta a soltura automaticamente no vídeo sintético (primeiro movimento).", "1.00s (quadro 10) — detecção automática"),
            ("Ajuste manual do intervalo, em segundos.", "ajustado manualmente"),
            ("O mesmo ajuste, em quadros.", "ajustado manualmente"),
            ("Início informado duas vezes (segundos e quadro).", "Erro no intervalo útil"),
            ("Fim antes do início.", "Erro no intervalo útil"),
            ("Fim além da duração do vídeo.", "Erro no intervalo útil"),
            ("Grava o trial 1: dia 1, recorte automático, rotação 0° (suposição da equipe de que a plataforma não gira).", None),
            ("Grava o trial 2: dia 2, recorte a partir de 2 s, rotação de 90° (simula um protocolo que gire a plataforma, para a B.7).", None),
            ("Guarda o id do trial do dia 1 (da montagem dos vídeos de amostra).", None),
            ("Guarda o id do trial do dia 2.", None),
            ("Grava o trial do vídeo completo com o intervalo ajustado à mão: a detecção automática pega a mão do experimentador aos 4,4 s, e a soltura real é aos 81,5 s, quando a caixa de partida é levantada.", "81.50s (quadro 2038) a 270.00s (quadro 6750) — ajustado manualmente"),
            ("Guarda o id do trial completo em `$tc`.", None),
            ("Tenta gravar o mesmo vídeo de novo, como outro dia.", "Este vídeo já foi carregado como trial (mesmo conteúdo, hash …)"),
            ("Gravar exige experimento e montagem juntos; com só um, o comando recusa em vez de deixar de gravar em silêncio.", "Para salvar o trial, informe --experiment-id e --maze-config-id juntos"),
            ("Auditoria do que ficou gravado: hash, dia, rotação, início e fim do intervalo e se o ajuste foi manual.", None),
            ("Testes do Cenário 3 e da regra de tempo zero no início do recorte.", None),
        ],
    ),
    "B.7": dict(
        titulo="Rotação da plataforma e referencial da sala",
        sobre="O índice de um buraco depende de como a montagem foi marcada; para o animal, o que importa é a posição na sala. O sistema converte entre três referenciais (imagem, plataforma e sala) usando a rotação de cada trial, para comparar trials de dias diferentes.",
        cmds=[
            ("Mostra o alvo do trial 1 na plataforma e na sala.", None),
            ("Mesmo alvo físico no trial 2, girado 90°: índice diferente, `target_angle_deg_room` igual.", "mesmo ângulo de sala nos dois trials"),
            ("Corrige a rotação para −90°. O `--` impede que o número negativo seja lido como opção.", "gravada como 270°"),
            ("Confere a rotação corrigida.", "270°"),
            ("Apaga a rotação do trial 2 direto no banco, simulando um trial sem rotação registrada.", None),
            ("Trial sem rotação é recusado: nunca vira 0° em silêncio.", "recusa citando o número do trial"),
            ("Volta a rotação para 90°.", None),
            ("Ida e volta índice → sala → índice para todos os buracos, com vários N, rotações e ângulos iniciais.", None),
        ],
    ),
    "B.8": dict(
        titulo="Métricas em cm, bloqueio sem escala e recalibração",
        sobre="Com escala e intervalo útil, calcula distância (cm), velocidade média (cm/s) e eficiência de rota a partir de uma trajetória. Mostra também os bloqueios (sem escala, escala de outra montagem, resolução diferente) e a regra de que recalibrar torna obsoletos os resultados antigos.",
        cmds=[
            ("Calcula as métricas do trial 1 com a trajetória de exemplo. Montagem, escala e intervalo vêm do próprio trial.", "distância, velocidade e \"samples_outside_interval\": 0"),
            ("Lista os resultados do trial e marca o atual.", None),
            ("O trial 2 começa em 2 s: a amostra de 0 s fica de fora.", "\"samples_outside_interval\": 1 e metade da distância"),
            ("Cria uma segunda montagem, sem calibração e sem janela.", None),
            ("Guarda o id dessa montagem em `$maze0`.", None),
            ("Pede as métricas do trial 1 com a montagem errada.", "O trial #… é da montagem #…, não da #…"),
            ("Grava o vídeo sintético como trial da montagem sem escala.", None),
            ("Guarda o id desse trial em `$t0`.", None),
            ("Sem escala, o cálculo é bloqueado antes de abrir o vídeo.", "A montagem … exige calibração"),
            ("Vídeo com resolução diferente da do trial (seria outra câmera).", "recusa citando as duas resoluções"),
            ("Refaz a calibração da montagem.", None, I),
            ("O resultado anterior aparece como obsoleto, porque foi calculado com a escala antiga.", "obsoleto"),
            ("Reprocessa com a escala nova.", None),
            ("Confere que voltou a ficar atual.", "atual"),
            ("Testes de bloqueio, escala e obsolescência.", None),
        ],
    ),
    "B.9": dict(
        titulo="Anotação de quadros para o modelo de pose",
        sobre="Para treinar o modelo que encontra focinho, centro do corpo e base da cauda, pessoas marcam esses pontos em quadros escolhidos. Esta etapa escolhe os quadros, confere a cobertura por região e divide os dados em treino, validação e teste sem misturar trials. Nesta demonstração, a anotação é simulada.",
        cmds=[
            ("Varre o vídeo, acha o animal por contraste e escolhe quadros cobrindo centro, borda e proximidade dos buracos, com 1 s entre eles. Exporta PNGs prontos para o SLEAP.", "contagem por região; “FALTARAM quadros” é normal em vídeos de 15 s"),
            ("O mesmo para o segundo vídeo.", None),
            ("Rodar de novo no mesmo trial é recusado: os quadros podem já estar anotados.", "recusa sugerindo --overwrite"),
            ("Amostra o vídeo completo só dentro do intervalo do trial (quadros 2038 a 6750); sem isso, a mão e a caixa de partida entrariam como “animal”. Leva cerca de 30 s.", "animal em ~99% dos quadros; borda 30/30, buraco 40/40, centro ~18/30 (o animal evita o centro)"),
            ("Gera `anotacoes.csv` como se os três pontos tivessem sido marcados na posição estimada. Na rodada real, esse arquivo vem do `pose import-slp`.", "cerca de 115 quadros com anotacao SIMULADA"),
            ("Conta os quadros anotados por região, cada trial com a sua própria montagem (aqui, duas câmeras).", "Cobertura OK: as três regiões têm quadros anotados."),
            ("Divide por trial: com 3 trials, um trial inteiro em cada conjunto.", "treino, validacao e teste com 1 trial cada"),
            ("Confere a divisão gerada.", "nenhum trial em mais de um conjunto"),
            ("Cria à mão um manifesto de divisão válido.", None),
            ("Confere o manifesto válido.", "passa"),
            ("Cria um manifesto em que o trial `aaa` aparece em treino e em teste.", None),
            ("Confere o manifesto vazado.", "Vazamento entre conjuntos … trial aaa em teste, treino."),
            ("Testes do US-06, incluindo leitura de projetos `.slp` e divisão com 3 ou mais trials.", None),
        ],
    ),
    "B.10": dict(
        titulo="Ambiente e treino do modelo de pose",
        sobre="O ferramental de treino: diagnóstico da máquina, plano de onde treinar, pacote congelado dos dados e treino com registro completo. O modelo real ainda não foi treinado: faltam a anotação real e uma GPU NVIDIA.",
        cmds=[
            ("Diagnostica GPU, VRAM, RAM e driver, e grava o relatório mesmo se a máquina for recusada.", "sem NVIDIA: o motivo da recusa"),
            ("Monta o plano de treino a partir do relatório, com a GPU institucional em situação desconhecida.", "Plano: pending"),
            ("GPU institucional disponível.", "Plano: selected | local: institucional"),
            ("Sem GPU institucional, só sobra a nuvem, que exige a resposta D4.", "Plano: blocked"),
            ("Com uma referência D4 fictícia, a nuvem é liberada.", "Plano: selected | local: kaggle"),
            ("Mostra o plano gravado: nenhum upload feito, e só quadros rotulados podem ir à nuvem, nunca vídeos.", "\"uploads_performed\": false"),
            ("Sem NVIDIA, o treino é recusado antes de qualquer outra coisa.", "Treino bloqueado: nvidia-smi não encontrado"),
            ("Pacote congelado, treino de uma época em CPU, manifesto e versionamento dos pesos.", None),
        ],
    ),
    "B.11": dict(
        titulo="Avaliação por região e inferência local",
        sobre="Avalia o modelo por região (centro, borda, buracos) e roda a inferência offline: para cada quadro do intervalo útil, o modelo devolve a pose. Depende do modelo do US-07, então ao vivo só aparece a recusa de um modelo incompleto.",
        cmds=[
            ("Cria a pasta de um “modelo” que parou no meio do treino.", None),
            ("Escreve um manifesto com `status: running`.", None),
            ("Tenta inferir com esse modelo.", "Modelo local inválido, sem ler o vídeo"),
            ("Critério de meio corpo: erro de cada ponto dividido pelo comprimento do corpo abaixo de 0,5, no global e em cada região.", None),
            ("Inferência sequencial (sem seek), conferência de hash e bloqueio de rede.", None),
        ],
    ),
    "B.12": dict(
        titulo="Série de posição e orientação da cabeça",
        sobre="A série de pose é o centro do pipeline: um arquivo Parquet com uma linha por quadro do intervalo útil, a posição de focinho, centro e cauda em cm, a orientação da cabeça θ e marcas de validade. Tudo o que vem depois (eventos e métricas) lê só esse arquivo. Aqui a pose é simulada.",
        cmds=[
            ("Caminho da pasta da inferência simulada do trial completo.", None),
            ("Inferência simulada sobre os ~4.700 quadros do intervalo: acha o centro do corpo por contraste, põe focinho e cauda no eixo do movimento e injeta três lacunas (3 quadros, 15 quadros e cerca de 7% do intervalo). Grava `pose.csv` e `execucao.json` no formato do `pose infer`. Leva cerca de 30 s.", "lista das lacunas; anote os quadros da lacuna longa do focinho"),
            ("Gera a série: confere trial, hash, montagem e fps, converte px→cm e aplica o tratamento da US-10.", "4713 quadros, 15 sem pose válida, cobertura ~92,7%, 2 trechos sinalizados"),
            ("Guarda numa variável um pequeno script Python que lê e resume a série. É usado de novo na B.13.", None),
            ("Caminho do arquivo da série.", None),
            ("Mostra contrato, escala e trechos da série: a lacuna curta interpolada e o focinho ausente (`nan`, sem repetir o quadro anterior).", None),
            ("Guarda o id da execução que gerou a série.", None),
            ("Mostra o que ficou registrado: modelo `simulado-demo`, hash do `pose.csv`, escala, intervalo e parâmetros.", None),
            ("Usa a pose do trial completo para o trial 1.", "A inferência … é do trial #<tc>, não do #<t1>."),
            ("θ concorda com a direção do deslocamento; o contrato é conferido na escrita e na leitura.", None),
        ],
    ),
    "B.13": dict(
        titulo="Suavização, interpolação e revisão de falhas de pose",
        sobre="Pose real tem falhas. O sistema suaviza, preenche as lacunas curtas por interpolação e manda as longas para revisão humana, numa janela que abre direto no trecho problemático. A cobertura (fração de quadros com os três pontos) diz se a qualidade é suficiente.",
        cmds=[
            ("Mostra os parâmetros do tratamento no YAML: cobertura mínima de 0,98, lacuna curta de até 5 quadros e mediana de 5 quadros.", None),
            ("Janela de revisão, aberta no trecho 1 (focinho): `d` avança um quadro, clique marca o ponto, `Enter` dá o trecho por revisado, `s` salva. Duas marcações bastam: o resto vira lacunas curtas e é interpolado.", "2 pontos corrigidos, 2 trechos revisados, QUALIDADE INSUFICIENTE", I),
            ("Confere a série regenerada.", "nenhum quadro sem focinho"),
            ("Guarda o id da execução da revisão.", None),
            ("A revisão tem execução própria: trechos revisados, correções, usuário e nova cobertura.", "\"comando\": \"pose review\""),
            ("Cada ponto marcado à mão, com o quadro e a posição.", None),
            ("Tenta editar uma correção direto no banco.", "Correções de pose são imutáveis"),
            ("O trial completo aparece no catálogo com qualidade insuficiente; a mesma marca vai junto da distância e velocidade na B.17.", "INSUFICIENTE"),
            ("A marca de qualidade é calculada por uma visão do banco, nunca gravada à parte.", None),
            ("Regenera a série a partir do `pose.csv` com todas as correções.", "mesma cobertura"),
            ("Abre a revisão de novo.", "Nenhum trecho pendente de revisão"),
            ("Testes do tratamento, da janela de revisão e das correções, incluindo a ressalva de fps instável.", None),
        ],
    ),
    "B.14": dict(
        titulo="Proveniência das execuções e catálogo de trials",
        sobre="Toda métrica ou evento gravado aponta para uma execução que guarda modelo, limiares, parâmetros, commit e se o repositório estava limpo. O catálogo lista os trials e detecta vídeo movido ou alterado.",
        cmds=[
            ("Histórico completo de resultados do trial 1, cada um com seu `execucao_id`.", None),
            ("Guarda o id da execução mais recente.", None),
            ("Mostra a execução: modelo, limiares (o YAML inteiro, com hash), parâmetros, commit, `git_dirty` e `reproduzivel`.", "\"reproduzivel\": true"),
            ("Todas as execuções do trial 1 e do trial completo, de todas as etapas (métricas, série, revisão).", None),
            ("Tenta gravar uma métrica sem execução.", "violates not-null constraint"),
            ("Catálogo: trial, animal, sessão, fase, situação, cobertura, fps e situação do arquivo.", None),
            ("A sessão (o dia) é uma visão derivada dos trials.", None),
            ("Cria a pasta para onde o vídeo será movido.", None),
            ("Move e renomeia o vídeo 1.", None),
            ("O catálogo encontra o vídeo pelo conteúdo.", "vídeo movido ou renomeado"),
            ("Reprocessar com o vídeo no lugar novo funciona, porque o hash é o mesmo; o caminho novo fica registrado.", None),
            ("Devolve o vídeo ao lugar.", None),
            ("Faz uma cópia de segurança do vídeo sintético.", None),
            ("Troca o conteúdo do vídeo sintético mantendo o caminho.", None),
            ("O catálogo acusa a troca.", "conteúdo … difere do catalogado"),
            ("Restaura o vídeo sintético.", None),
            ("Relê cada vídeo e confere o hash completo (mais lento).", "ok em todos os trials"),
            ("Cria um arquivo não commitado, para “sujar” o repositório.", None),
            ("Processa com o repositório sujo.", "aviso de repositório sujo"),
            ("Guarda o id dessa execução.", None),
            ("Mostra a execução suja.", "\"git_dirty\": true e \"reproduzivel\": false"),
            ("Apaga o arquivo de teste.", None),
            ("Métrica e evento órfãos recusados, execução imutável, catálogo, arquivo movido ou alterado.", None),
        ],
    ),
    "B.15": dict(
        titulo="Detecção do evento de descoberta (D)",
        sobre="A descoberta é o primeiro momento em que o focinho chega perto de um buraco com a cabeça virada para ele. É calculada só a partir da série, com limiares do YAML (3 cm e 30°, provisórios).",
        cmds=[
            ("Mostra os limiares de descoberta no YAML.", None),
            ("Detecta as descobertas do trial completo.", "cerca de 12 buracos; o alvo (buraco 0) aos ~157 s da soltura"),
            ("Tira o vídeo do lugar.", None),
            ("Roda de novo sem o vídeo: o cálculo nunca o abre.", "mesmo resultado, sem erro"),
            ("Devolve o vídeo ao lugar.", None),
            ("Os eventos gravados, ligados ao buraco e à execução.", None),
            ("Guarda o id da execução de descoberta.", None),
            ("Mostra os limiares e parâmetros usados.", None),
            ("Cria um YAML à parte com limiares bem mais largos (20 cm, 90°).", None),
            ("Recalcula com esses limiares, sem tocar no vídeo nem no Parquet.", "a mesma lista ou mais buracos"),
            ("As duas execuções lado a lado.", None),
            ("Testes dos limiares, do cálculo e da prova de que o vídeo não é aberto.", None),
        ],
    ),
    "B.16": dict(
        titulo="Entrada, dwell e sequência de visitação",
        sobre="Entrada (E) é o focinho dentro do buraco por pelo menos 0,2 s. A diferença entre descoberta e entrada é a hesitação; dwell é quanto tempo o focinho ficou no buraco. A sequência de visitação ordena as entradas no referencial da sala e é a base da contagem de erros e da estratégia. Os limiares são decisões da equipe.",
        cmds=[
            ("Mostra a versão das definições e os limiares de entrada, tempo limite e erro.", "decisoes-equipe-2026-11-12-sem-G3, raio_fator 1.0, 0.2 s, 180 s"),
            ("Garante a migração 0009 (detalhes da entrada).", None),
            ("Detecta entradas, hesitação D→E e dwell. Código de saída 2 indica inconsistências registradas, não falha.", "cerca de 37 entradas; primeira entrada no alvo aos ~161 s (não censurada: < 180 s)"),
            ("Pega a pasta de saída mais recente.", None),
            ("Mostra a tabela de entradas: buraco, tempos, `delta_latency`, `delta_distance`, `dwell_s`.", None),
            ("Monta a sequência de visitação a partir das entradas gravadas.", None),
            ("Pega a pasta da sequência mais recente.", None),
            ("Mostra a sequência: ordem, buraco, ângulo na sala e alvo.", None),
            ("Guarda o id da execução de entrada.", None),
            ("Mostra os limiares usados, com a marca de decisão da equipe.", None),
            ("Calibração contra anotação manual (US-12): sem anotação, a rodada fica registrada como bloqueada.", "Bloqueado por D3, código de saída 2"),
            ("Latência com censura (US-16) e contagem de erros (US-17), pelos testes: ainda não têm comando.", None),
        ],
    ),
    "B.17": dict(
        titulo="Distância total e velocidade média",
        sobre="Uma distância (cm) e uma velocidade média (cm/s) por trial, a partir da série, com a fração interpolada e a ressalva de fps variável. São as colunas complementares que a exportação da US-25 levará ao `trials.csv`, convertidas para metros.",
        cmds=[
            ("Garante a migração 0010 (fração interpolada).", None),
            ("Calcula e grava distância e velocidade do trial completo.", "cerca de 1.107 cm em 188 s, 5,9 cm/s"),
            ("Tira o vídeo do lugar.", None),
            ("Roda de novo sem o vídeo.", "mesmo resultado, sem erro"),
            ("Devolve o vídeo ao lugar.", None),
            ("O resultado gravado, uma linha por execução.", None),
            ("Correlação com a distância medida à mão (r ≥ 0,95). Sem medida manual, registra a rodada como bloqueada.", "código de saída 2"),
            ("Testes do cálculo, da validação e do comando, incluindo fps variável e ausência que nunca vira zero.", None),
        ],
    ),
    "B.18": dict(
        titulo="Trial de referência e teste de regressão",
        sobre="Rede de segurança do projeto: um vídeo sintético versionado e o valor esperado de cada métrica. Se uma mudança no código alterar qualquer número, o teste falha dizendo qual métrica e quanto.",
        cmds=[
            ("Roda o teste de regressão sobre o trial de referência.", "10 passed, em cerca de 1,5 s"),
            ("Faz backup do esperado, troca `total_errors: 1` por `2` com um mini script Python e roda o teste.", "erros.total_errors: esperado 2, obtido 1"),
            ("Restaura o esperado e confirma que o teste volta a passar. Não pule este passo.", "10 passed"),
        ],
    ),
    "C": dict(
        titulo="Encerramento",
        sobre="Devolve o terminal e a pasta do projeto ao estado normal.",
        cmds=[
            ("Remove as variáveis de banco deste terminal; os comandos voltam a usar o banco de desenvolvimento do `.env`.", None),
            ("Confere que os vídeos movidos voltaram ao lugar.", "True duas vezes"),
            ("Nada sobrando: arquivo de teste apagado e esperado da B.18 restaurado.", "lista vazia"),
            ("Opcional: apaga o banco de demonstração.", None),
        ],
    ),
}

CARDS = {
    "B.1": ("—", 0), "B.2": ("—", 0),
    "B.3": ("US-04", 1), "B.4": ("US-01", 1), "B.5": ("US-02", 1), "B.6": ("US-03", 1),
    "B.7": ("US-05", 1), "B.8": ("US-02 · US-03", 1), "B.9": ("US-06", 1),
    "B.10": ("US-07", 2), "B.11": ("US-08", 2), "B.12": ("US-09", 2), "B.13": ("US-10", 2),
    "B.14": ("US-27", 2), "B.15": ("US-11", 2),
    "B.16": ("US-12 · US-13 · US-14 · US-15 · US-16 · US-17", 3),
    "B.17": ("US-18", 3), "B.18": ("US-28", 3),
}

PIPELINE = [
    ("Vídeo .mp4", "US-01", "B.4", "metadados + hash → trials", 1),
    ("Montagem", "US-04", "B.3", "centro, buracos, alvo → maze_configs", 1),
    ("Escala px→cm", "US-02", "B.5", "cm/px na montagem", 1),
    ("Intervalo útil", "US-03", "B.6", "soltura → fim; t = 0 na soltura", 1),
    ("Referencial da sala", "US-05", "B.7", "rotação do trial", 1),
    ("Anotação", "US-06", "B.9", "quadros + anotacoes.csv", 1),
    ("Treino e inferência", "US-07 · US-08", "B.10", "modelo → pose.csv", 2),
    ("Série de pose", "US-09", "B.12", "trial_<id>.parquet", 2),
    ("Tratamento e revisão", "US-10", "B.13", "interpolação, cobertura", 2),
    ("Descoberta (D)", "US-11", "B.15", "evento_buraco", 2),
    ("Entrada (E) e dwell", "US-13 · US-14", "B.16", "entries.csv", 3),
    ("Sequência de visitação", "US-15", "B.16", "sequencia.csv (sala)", 3),
    ("Latência e erros", "US-16 · US-17", "B.16", "primary_* / total_*", 3),
    ("Distância e velocidade", "US-18", "B.17", "trial_results", 3),
]

GLOSSARIO = [
    ("Trial", "Uma tentativa do animal no labirinto: um vídeo, gravado no banco com dia, ordem no dia, intervalo útil e rotação."),
    ("Montagem", "A geometria do labirinto vista por uma câmera: centro, raio, N buracos, alvo e escala px→cm."),
    ("Intervalo útil", "Trecho do vídeo da soltura ao fim. O tempo zero de todas as métricas é a soltura (S)."),
    ("Referencial da sala", "Ângulo fixo de cada buraco na sala, independente de como a plataforma foi girada. Permite comparar dias."),
    ("Pose", "Posição de três pontos do corpo (focinho, centro do corpo, base da cauda) em cada quadro."),
    ("Série de pose", "O Parquet `trial_<id>.parquet`: uma linha por quadro, posições em cm, θ da cabeça e marcas de validade. Contrato de entrada de eventos e métricas."),
    ("Cobertura", "Fração dos quadros com os três pontos presentes (contando interpolados e corrigidos). Mínimo de 0,98."),
    ("Descoberta (D)", "Focinho perto do buraco (3 cm) e cabeça virada para ele (30°)."),
    ("Entrada (E)", "Focinho dentro do buraco por pelo menos 0,2 s. D→E é a hesitação."),
    ("Dwell", "Quanto tempo o focinho ficou dentro do buraco."),
    ("Censura", "Quando o animal não chega ao alvo até o tempo limite (180 s), a latência é registrada como censurada, não como zero."),
    ("Execução", "Registro imutável de cada processamento: modelo, limiares, parâmetros, commit e se o repositório estava limpo."),
    ("Limiares", "Valores de `configs/default.yaml`. Sem contato com o laboratório, são decisões da equipe (`versao_definicoes: decisoes-equipe-2026-11-12-sem-G3`)."),
]

PENDENCIAS = [
    ("Modelo de pose", "Não treinado: falta a anotação real e uma GPU NVIDIA. A pose da demonstração é simulada (B.12)."),
    ("Limiares", "Decisões da equipe, sem G3. A descoberta (3 cm / 30°) continua provisória."),
    ("Anotação manual", "Não existe, nem do laboratório nem pública. Todas as comparações contra anotação manual foram puladas."),
    ("Medidas físicas", "92 cm e 5 cm são valores típicos; um fator de escala não muda os hazard ratios."),
    ("US-16 e US-17", "Calculadas e testadas, ainda sem comando; a exportação `trials.csv` é a US-25."),
    ("US-28", "Fixture sintético; o teste antes do merge é regra de revisão (não há CI)."),
    ("Cadastro", "Usuário, experimento e animal ainda são criados direto no banco."),
]


def extrair(path: Path) -> list[tuple[str, str, list[str]]]:
    texto = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    secoes: list[tuple[str, str, list[str]]] = []
    atual = None
    em_codigo = False
    buf: list[str] = []
    for linha in texto.split("\n"):
        if not em_codigo:
            if linha.startswith("## O que dizer") or linha.startswith("## Se algo"):
                atual = None
                continue
            m = re.match(r"^### ([AB]\.\d+)\s+(.*)$", linha)
            if m:
                atual = (m.group(1), m.group(2), [])
                secoes.append(atual)
                continue
            if linha.startswith("## Parte C"):
                atual = ("C", "Encerramento", [])
                secoes.append(atual)
                continue
        if linha.startswith("```powershell"):
            em_codigo, buf = True, []
            continue
        if em_codigo and linha.startswith("```"):
            em_codigo = False
            if atual is not None:
                atual[2].append("\n".join(buf))
            continue
        if em_codigo:
            buf.append(linha)
    return secoes


def tipo(cmd: str) -> str:
    primeira = cmd.lstrip()
    if "uv run pytest" in cmd or primeira.startswith("uv run ruff"):
        return "teste"
    if primeira.startswith("uv run barnes"):
        return "barnes"
    if "psql" in cmd:
        return "sql"
    if "@'" in cmd or "uv run python" in cmd:
        return "python"
    return "shell"


ROTULO = {"barnes": "barnes", "sql": "SQL", "teste": "teste", "python": "Python", "shell": "PowerShell"}


def inline(texto: str) -> str:
    esc = html.escape(texto, quote=False)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)


def maze_svg() -> str:
    n, r, cx, cy = 20, 78, 100, 100
    furos = []
    alvo, errado = 5, 9
    pts = {}
    for k in range(n):
        a = math.radians(k * 360 / n - 90)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        pts[k] = (x, y)
        cls = "hole target" if k == alvo else "hole"
        furos.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="5.5"/>')
    ex, ey = pts[errado]
    tx, ty = pts[alvo]
    caminho = (
        f'<path class="track" d="M{cx},{cy} C{cx+18},{cy+30} {ex-30},{ey-20} {ex*0.9+cx*0.1:.1f},{ey*0.9+cy*0.1:.1f} '
        f'S{tx-10},{ty+40} {tx*0.92+cx*0.08:.1f},{ty*0.92+cy*0.08:.1f}"/>'
    )
    return (
        '<svg class="maze" viewBox="0 0 200 200" role="img" aria-label="Labirinto de Barnes com 20 buracos, '
        'trajeto passando por um buraco errado até o alvo">'
        f'<circle class="platform" cx="{cx}" cy="{cy}" r="92"/>'
        + caminho
        + "".join(furos)
        + f'<circle class="release" cx="{cx}" cy="{cy}" r="4"/>'
        + "</svg>"
    )


def gerar(secoes, saida: Path) -> None:
    partes_html = []
    toc = {"A": [], "B": [], "C": []}
    total = 0
    contagem = {"barnes": 0, "sql": 0, "teste": 0, "python": 0, "shell": 0}
    for sid, titulo_md, blocos in secoes:
        info = SECOES.get(sid)
        if info is None:
            raise SystemExit(f"Seção sem explicação: {sid}")
        if len(info["cmds"]) != len(blocos):
            raise SystemExit(f"{sid}: {len(blocos)} blocos no roteiro, {len(info['cmds'])} explicações")
        card, sprint = CARDS.get(sid, ("", None))
        anchor = "s-" + sid.replace(".", "-").lower()
        toc[sid[0]].append((anchor, sid, info["titulo"], card))
        meta = []
        if card and card != "—":
            meta.append(f'<span class="card-tag">{html.escape(card)}</span>')
        if sprint:
            meta.append(f'<span class="sprint s{sprint}">Sprint {sprint}</span>')
        itens = []
        for i, (bloco, expl) in enumerate(zip(blocos, info["cmds"], strict=True)):
            explicacao, esperado = expl[0], expl[1]
            interativo = len(expl) > 2 and expl[2]
            k = tipo(bloco)
            if sid == "B.18" and i == 1:
                k = "teste"
            contagem[k] += 1
            total += 1
            linhas = bloco.split("\n")
            codigo = html.escape(bloco)
            pre = f'<pre><code>{codigo}</code></pre>'
            if len(linhas) > 10:
                pre = (f'<details class="script"><summary>Ver o script ({len(linhas)} linhas)</summary>'
                       f"{pre}</details>")
            flags = f'<span class="kind k-{k}">{ROTULO[k]}</span>'
            if interativo:
                flags += '<span class="kind k-janela">abre janela</span>'
            esp = (f'<p class="expect"><span>Esperado</span> {inline(esperado)}</p>' if esperado else "")
            itens.append(
                f'<li class="cmd" data-kind="{k}">'
                f'<div class="cmd-head">{flags}<button class="copy" type="button" '
                f'aria-label="Copiar comando">Copiar</button></div>'
                f'<p class="why">{inline(explicacao)}</p>'
                f'<div class="code">{pre}</div>{esp}</li>'
            )
        lista = f'<ol class="cmds">{"".join(itens)}</ol>' if itens else ""
        partes_html.append(
            f'<section class="step" id="{anchor}">'
            f'<header class="step-head"><span class="sid">{sid}</span>'
            f'<div><h3>{html.escape(info["titulo"])}</h3>'
            f'<div class="meta">{"".join(meta)}</div></div></header>'
            f'<p class="about">{inline(info["sobre"])}</p>{lista}</section>'
        )
        if sid == "A.5":
            partes_html.append('<h2 class="part" id="parte-b">Parte B · Demonstração</h2>')
        if sid == "B.18":
            partes_html.append('<h2 class="part" id="parte-c">Parte C · Depois da reunião</h2>')

    def toc_html():
        blocos = []
        nomes = {"A": ("parte-a", "Parte A · Preparação"), "B": ("parte-b", "Parte B · Demonstração"),
                 "C": ("parte-c", "Parte C · Encerramento")}
        for parte, itens in toc.items():
            ancora, nome = nomes[parte]
            lis = "".join(
                f'<li><a href="#{a}"><span class="toc-id">{s}</span>{html.escape(t)}</a></li>'
                for a, s, t, _ in itens
            )
            blocos.append(f'<p class="toc-part"><a href="#{ancora}">{nome}</a></p><ol>{lis}</ol>')
        return "".join(blocos)

    fluxo = []
    for i, (nome, card, sec, artefato, sprint) in enumerate(PIPELINE):
        anchor = "s-" + sec.replace(".", "-").lower()
        fluxo.append(
            f'<li class="stage s{sprint}"><a href="#{anchor}">'
            f'<span class="stage-n">{i + 1:02d}</span>'
            f'<span class="stage-name">{html.escape(nome)}</span>'
            f'<span class="stage-card">{html.escape(card)} · {sec}</span>'
            f'<span class="stage-out">{html.escape(artefato)}</span></a></li>'
        )
    gloss = "".join(f"<div><dt>{html.escape(t)}</dt><dd>{inline(d)}</dd></div>" for t, d in GLOSSARIO)
    pend = "".join(f"<li><strong>{html.escape(t)}.</strong> {inline(d)}</li>" for t, d in PENDENCIAS)
    filtros = "".join(
        f'<button type="button" class="chip k-{k}" data-kind="{k}" aria-pressed="true">'
        f'{ROTULO[k]} <span class="n">{contagem[k]}</span></button>'
        for k in ("barnes", "sql", "teste", "python", "shell")
    )

    pagina = (TEMPLATE
              .replace("%%MAZE%%", maze_svg())
              .replace("%%TOTAL%%", str(total))
              .replace("%%FLUXO%%", "".join(fluxo))
              .replace("%%TOC%%", toc_html())
              .replace("%%FILTROS%%", filtros)
              .replace("%%GLOSS%%", gloss)
              .replace("%%PEND%%", pend)
              .replace("%%SECOES%%", "".join(partes_html)))
    # Página completa (doctype e head), para abrir direto no navegador.
    head, body = pagina.split("</style>", 1)
    completa = (
        '<!doctype html>\n<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        + head
        + "</style>\n</head>\n<body>\n"
        + body.strip()
        + "\n</body>\n</html>\n"
    )
    saida.write_bytes(completa.encode("utf-8"))
    print(f"{total} comandos em {len(secoes)} seções -> {saida}")


TEMPLATE = Path(__file__).with_name("guia_template.html").read_text(encoding="utf-8")

if __name__ == "__main__":
    raiz = Path(__file__).resolve().parents[1]
    gerar(
        extrair(raiz / "docs" / "ROTEIRO-DEMONSTRACAO.md"),
        raiz / "docs" / "roteiro-demonstracao.html",
    )

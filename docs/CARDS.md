# Cards de User Stories — Aprendizado espacial no labirinto de Barnes

**Backlog executável · 30 cards · 5 sprints de 2 semanas**
Cliente: LNBio · Equipe: 5 integrantes

Cards gerados a partir das histórias de [Apresentacao.md](Apresentacao.md), dos critérios de aceite e do contexto técnico de [definicao-projeto.md](definicao-projeto.md), seguindo o template de [estrutura_cards_scrum.md](estrutura_cards_scrum.md).

---

## Como ler estes cards

- **Numeração.** `[US-01]` a `[US-30]`, sequencial. **Não corresponde mais um-para-um às histórias 1 a 30 das fontes:** três histórias saíram de escopo por já existirem no laboratório (ver **Fora de escopo**, ao final) e três cards foram divididos em dois por excederem o tamanho máximo da régua de estimativa. O total voltou a 30 por coincidência aritmética — três remoções, três divisões. A tabela de rastreabilidade abaixo liga cada card à sua história de origem.
- **Épicos.** Mantidos os nove épicos originais (A–I). O guia sugere de 3 a 6, mas os épicos aqui já correspondem a módulos reais de `src/barnes/` e a fronteiras de responsabilidade da equipe.
- **Limiares operacionais.** Todo card que depende de um limiar (distância, ângulo, dwell, definição de erro, critérios de estratégia) o trata como **parâmetro em `configs/`**, nunca como constante no código. Os valores vêm do portão **G3** e ficam registrados em `docs/definicoes-metricas.md`, com aceite por escrito do PI. Enquanto G3 não fecha, os cards são desenvolvíveis com valores provisórios, mas **não são aceitáveis**.
- **Divergência entre as fontes.** Nas histórias 21, 22 e 25 as duas fontes discordam. `definicao-projeto.md` v0.3 previa ANOVA-RM, log-rank e CSV genérico; `Apresentacao.md` prevê regressão de Cox, incidência cumulativa com forest plot e compatibilidade com `trials.csv`/`probes.csv`. **Os cards seguem o `Apresentacao.md`**, por refletir o pipeline estatístico que o laboratório já usa (`barnes_maze.py`, lifelines).
- **Definição de Pronto.** Adaptada ao domínio: o projeto é um pipeline Python offline com saída em CSV/Parquet/SQLite, não uma aplicação web. Os itens de DoD do template referentes a frontend e console foram substituídos pelos equivalentes deste contexto.
- **Vocabulário de eventos.** Herdado do pipeline existente: **S** = soltura, **D** = descoberta (encontrar), **E** = entrada. Fase primária = S→D; fase de decisão = D→E; período total = S→E.
- **Escala de estimativa.** Fibonacci: **3 (P) · 5 (M) · 8 (G) · 13 (GG)**. Os valores 1 e 2 não aparecem porque nenhum card deste projeto é trivial — todos carregam custo fixo de vídeo, calibração ou configuração. O valor 13 extrapola a escala sugerida no guia e é usado deliberadamente em dois cards, como sinalização de que devem ser fatiados. As estimativas foram **derivadas das tarefas**, não do enunciado da história: cada tarefa recebeu peso P (0,5), M (1) ou G (2) unidades, e a soma foi remapeada para a escala ancorando em US-15 = 3 pontos. O método está detalhado ao final.
- **Distribuição por sprint.** Os cinco sprints têm **6 cards cada**. Essa alocação difere da que consta em `Apresentacao.md` e `definicao-projeto.md`: quatro cards — **US-05, US-10, US-18 e US-24** — foram antecipados em um sprint. A justificativa de cada movimento está registrada nas regras de negócio do próprio card e resumida ao final deste documento.

---

# Épico A — Aquisição e calibração

### [US-01] Carga do vídeo do trial e leitura dos metadados

- **Épico / Módulo:** Aquisição e calibração (`src/barnes/io/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S1

#### Narrativa de Usuário
- **Como** operador do laboratório,
- **Quero** carregar o vídeo de um trial e ver o primeiro quadro junto dos metadados do arquivo,
- **Para que** eu confirme que o arquivo correto foi lido e íntegro antes de gastar tempo de processamento.

#### Regras de Negócio & Escopo
- [RN01] Após a carga, o sistema exibe resolução (px), fps **real medido** (não o declarado no contêiner), duração e número total de quadros.
- [RN02] O fps real é medido a partir dos carimbos de tempo dos quadros, não do cabeçalho do arquivo.
- [RN03] Se o fps for variável, o sistema emite aviso explícito e passa a usar carimbo de tempo por quadro como base temporal de todas as métricas.
- [RN04] Formatos suportados: os produzidos pela captura do LNBio, lidos via OpenCV/FFmpeg. Vídeo em `data/raw/` é tratado como somente leitura.
- [RN05] O arquivo recebe um hash de conteúdo no momento da carga, usado depois por [US-27] para detectar arquivo movido ou alterado.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — vídeo válido com fps constante**
  - **Dado que** o operador tem um trial gravado em `data/raw/`,
  - **Quando** ele executa a carga apontando para o arquivo,
  - **Então** o sistema exibe o primeiro quadro e imprime resolução, fps real medido, duração e número de quadros, sem aviso de fps variável.

- **Cenário 2: Fluxo alternativo — vídeo com taxa de quadros variável**
  - **Dado que** o vídeo foi gravado com fps variável (diferença > 1% entre intervalos de quadro),
  - **Quando** o operador executa a carga,
  - **Então** o sistema exibe o aviso *"fps variável detectado — usando carimbo de tempo por quadro"* e registra essa escolha nos metadados da execução.

- **Cenário 3: Tratamento de erro — arquivo ilegível ou corrompido**
  - **Dado que** o arquivo apontado não existe, está truncado ou tem codec não suportado,
  - **Quando** o operador executa a carga,
  - **Então** o sistema aborta com mensagem identificando o arquivo e a causa, sem criar registro parcial no banco.

#### Tarefas
- [ ] Levantar formatos, codecs e contêineres presentes no acervo do LNBio
- [ ] Implementar o leitor de vídeo em `src/barnes/io/` com OpenCV/FFmpeg
- [ ] Implementar a medição de fps real a partir dos carimbos de tempo dos quadros
- [ ] Implementar a detecção de fps variável e a troca para base temporal por carimbo
- [ ] Implementar o cálculo e a persistência do hash de conteúdo do arquivo
- [ ] Implementar a exibição do primeiro quadro e do resumo de metadados
- [ ] Escrever testes para fps constante, fps variável e arquivo corrompido
- [ ] Expor o comando na CLI e documentar seu uso

#### Definição de Pronto (DoD Específica do Card)
- [ ] Leitor de vídeo implementado em `src/barnes/io/` com medição de fps real
- [ ] Testes unitários cobrindo fps constante, fps variável e arquivo inválido
- [ ] Hash do arquivo calculado e persistido
- [ ] Executável pela CLI com um comando documentado
- [ ] Revisado por outro integrante e integrado à branch principal

---

### [US-02] Calibração da escala px→cm por dois pontos conhecidos

- **Épico / Módulo:** Aquisição e calibração (`src/barnes/io/`, `configs/montagens/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 3 Pontos · 1,5–2 dias
- **Sprint:** S1

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** calibrar a escala do vídeo marcando dois pontos de distância real conhecida,
- **Para que** todas as métricas do estudo saiam em centímetros e sejam comparáveis com a literatura e com a anotação manual.

#### Regras de Negócio & Escopo
- [RN01] O pesquisador marca dois pontos sobre um quadro de referência e informa a distância real entre eles, em centímetros.
- [RN02] O fator de escala (cm/px) é salvo na **montagem** (`configs/montagens/*.yaml`), não no trial — vale para todos os trials da mesma configuração de câmera.
- [RN03] Sem escala calibrada, o sistema recusa o cálculo de qualquer métrica com unidade métrica (distância, velocidade, eficiência de rota).
- [RN04] O erro de medição aceito é **< 3%** contra uma distância real independente da usada na calibração (critério da seção 10).
- [RN05] Recalibrar sobrescreve a escala da montagem e invalida as métricas já calculadas com a escala anterior — as execuções antigas permanecem no banco, marcadas com a escala que usaram.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — calibração aceita**
  - **Dado que** o pesquisador carregou um trial com marcador de dimensão conhecida no enquadramento,
  - **Quando** ele marca os dois extremos do marcador e informa a distância real em cm,
  - **Então** o sistema calcula e salva o fator cm/px na montagem e exibe o valor resultante.

- **Cenário 2: Verificação de exatidão**
  - **Dado que** a escala foi calibrada com um marcador,
  - **Quando** o pesquisador mede no sistema uma **segunda** distância real conhecida da cena (por exemplo, o diâmetro da plataforma),
  - **Então** o valor medido difere do real em **menos de 3%**.

- **Cenário 3: Tratamento de erro — cálculo sem escala**
  - **Dado que** a montagem não tem escala calibrada,
  - **Quando** o operador solicita o processamento de um trial,
  - **Então** o sistema bloqueia a execução com a mensagem de que a montagem exige calibração, indicando o comando para calibrá-la.

#### Tarefas
- [ ] Definir o formato do bloco de escala no YAML de montagem
- [ ] Implementar a marcação interativa de dois pontos em janela OpenCV
- [ ] Implementar o cálculo do fator cm/px e sua gravação na montagem
- [ ] Implementar o bloqueio de métricas métricas quando não há escala calibrada
- [ ] Gerar imagem sintética de escala conhecida para uso em teste
- [ ] Escrever teste verificando erro < 3% contra distância independente
- [ ] Implementar a marcação das execuções antigas com a escala que usaram
- [ ] Registrar no manual o procedimento de calibração e de recalibração

#### Definição de Pronto (DoD Específica do Card)
- [ ] Rotina de calibração interativa (janela OpenCV) implementada
- [ ] Escala persistida em `configs/montagens/*.yaml`, legível e versionável
- [ ] Teste automatizado verificando o erro < 3% em imagem sintética de escala conhecida
- [ ] Bloqueio de métricas métricas sem escala coberto por teste
- [ ] Procedimento descrito em `docs/manual-usuario.md`

---

### [US-03] Recorte do intervalo útil do trial

- **Épico / Módulo:** Aquisição e calibração (`src/barnes/io/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S1

#### Narrativa de Usuário
- **Como** operador,
- **Quero** recortar o intervalo útil do trial, descartando o tempo antes da soltura e depois da fuga,
- **Para que** as métricas reflitam apenas o comportamento de busca e não o tempo de manipulação do animal.

#### Regras de Negócio & Escopo
- [RN01] Início e fim do intervalo são configuráveis por trial, em segundos ou número de quadro.
- [RN02] **Nenhuma** métrica, evento ou ponto de trajetória é calculado fora do intervalo útil.
- [RN03] O instante de início (evento **S**, soltura) é detectado automaticamente quando possível — por exemplo, pela remoção do cilindro ou pelo primeiro movimento do animal — e sempre pode ser corrigido manualmente.
- [RN04] O intervalo efetivamente usado é persistido no registro do trial e reportado nas saídas, para auditoria.
- [RN05] O tempo zero de todas as latências é o início do intervalo útil, não o início do arquivo de vídeo.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — detecção automática confirmada**
  - **Dado que** um trial foi carregado e a detecção automática propôs um instante de soltura,
  - **Quando** o operador confirma o intervalo proposto,
  - **Então** o sistema grava início e fim no registro do trial e todas as métricas subsequentes usam o início como tempo zero.

- **Cenário 2: Fluxo alternativo — ajuste manual do intervalo**
  - **Dado que** a detecção automática errou o instante de soltura,
  - **Quando** o operador informa manualmente início e fim,
  - **Então** o sistema adota os valores informados, marca o intervalo como "ajustado manualmente" e registra isso na execução.

- **Cenário 3: Validação do recorte**
  - **Dado que** um trial tem intervalo útil definido entre 12 s e 312 s,
  - **Quando** as métricas são calculadas,
  - **Então** nenhum evento de buraco, ponto de trajetória ou parcela de distância originado fora desse intervalo aparece nas saídas.

#### Tarefas
- [ ] Definir a representação do intervalo útil (segundos e número de quadro) no registro do trial
- [ ] Implementar a aplicação do recorte a montante de todo o pipeline
- [ ] Implementar a heurística de detecção automática do evento S (soltura)
- [ ] Implementar o ajuste manual de início e fim, com marcação de "ajustado manualmente"
- [ ] Implementar o tempo zero das latências ancorado no início do intervalo
- [ ] Escrever teste garantindo que nada fora do intervalo entra nas métricas
- [ ] Validar a heurística de detecção nos 3 trials representativos de G1
- [ ] Documentar o comportamento em `docs/manual-usuario.md`

#### Definição de Pronto (DoD Específica do Card)
- [ ] Recorte implementado e aplicado a montante de todo o pipeline
- [ ] Heurística de detecção automática do evento S implementada com fallback manual
- [ ] Teste automatizado garantindo que nada fora do intervalo entra nas métricas
- [ ] Intervalo persistido no registro do trial
- [ ] Comportamento documentado em `docs/manual-usuario.md`

---

# Épico B — Geometria do labirinto

### [US-04] Configuração paramétrica da geometria do Barnes

- **Épico / Módulo:** Geometria (`src/barnes/geometry/`, `configs/montagens/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S1

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** ajustar o círculo da plataforma, gerar os buracos por número e ângulo inicial, marcar o buraco-alvo e salvar tudo como uma montagem,
- **Para que** eu configure a geometria uma única vez e a reaproveite em todos os trials do estudo.

#### Regras de Negócio & Escopo
- [RN01] A geometria é **paramétrica**, definida por quatro números: centro (x, y), raio, número de buracos **N** e ângulo inicial. Não há editor de polígonos.
- [RN02] Os buracos são gerados igualmente espaçados sobre a circunferência, indexados de 0 a N−1 no sentido definido pelo ângulo inicial.
- [RN03] O buraco-alvo é identificado pelo seu índice na montagem.
- [RN04] A montagem é salva em `configs/montagens/*.yaml`, em formato legível por humanos e versionável em Git.
- [RN05] Carregar uma montagem reaplica geometria, alvo e escala px→cm de [US-02] sem qualquer nova interação.
- [RN06] O raio de cada buraco e as zonas de proximidade derivam da geometria e alimentam os eventos do Épico D.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — criar e salvar uma montagem**
  - **Dado que** o pesquisador tem um quadro de referência da plataforma,
  - **Quando** ele ajusta centro, raio, N e ângulo inicial e marca o índice do alvo,
  - **Então** os buracos desenhados sobre o quadro coincidem visualmente com os buracos reais e a montagem é gravada em `configs/montagens/*.yaml`.

- **Cenário 2: Reaproveitamento da montagem**
  - **Dado que** existe uma montagem salva,
  - **Quando** o operador processa um novo trial informando essa montagem,
  - **Então** geometria, buraco-alvo e escala são aplicados automaticamente, sem nenhuma etapa interativa.

- **Cenário 3: Tratamento de erro — parâmetros inconsistentes**
  - **Dado que** o pesquisador informa N ≤ 2, raio não positivo ou índice de alvo fora de 0..N−1,
  - **Quando** ele tenta salvar a montagem,
  - **Então** o sistema recusa a gravação e aponta qual parâmetro é inválido.

#### Tarefas
- [ ] Levantar com o laboratório o número de buracos e o diâmetro da plataforma (pergunta B2)
- [ ] Definir o esquema YAML da montagem (centro, raio, N, ângulo inicial, alvo, escala)
- [ ] Implementar a geração paramétrica dos buracos com Shapely
- [ ] Implementar a indexação dos buracos e a marcação do buraco-alvo
- [ ] Implementar a interface de ajuste com sobreposição sobre o quadro de referência
- [ ] Implementar a validação de parâmetros (N, raio, índice do alvo)
- [ ] Implementar a carga de montagem reaplicando geometria, alvo e escala
- [ ] Implementar as zonas de proximidade derivadas da geometria, para o Épico D
- [ ] Escrever testes de geração de buracos e de rejeição de parâmetros inválidos
- [ ] Versionar a montagem real do LNBio em `configs/montagens/`

#### Definição de Pronto (DoD Específica do Card)
- [ ] Módulo `geometry/` gerando buracos a partir dos quatro parâmetros, com Shapely
- [ ] Interface de ajuste (janela OpenCV) com sobreposição sobre o quadro de referência
- [ ] Esquema do YAML de montagem documentado
- [ ] Testes de geração de buracos e de validação de parâmetros inválidos
- [ ] Uma montagem real do LNBio versionada em `configs/montagens/`

---

### [US-05] Registro da rotação da plataforma e referencial da sala

- **Épico / Módulo:** Geometria (`src/barnes/geometry/`, `db/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S1

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** registrar a rotação da plataforma em cada trial e converter entre o referencial da plataforma e o da sala,
- **Para que** toda a análise longitudinal compare posições espaciais reais, e não índices de buraco que mudam a cada rotação.

#### Regras de Negócio & Escopo
- [RN01] A rotação de cada trial é gravada na coluna `trial.rotacao`, em graus, obrigatoriamente — ausência de valor é erro, não zero implícito.
- [RN02] O sistema converte, nos dois sentidos, entre **índice de buraco** (referencial da plataforma) e **posição angular na sala** (referencial fixo).
- [RN03] **Toda** análise longitudinal — sequência de visitação comparada entre trials, DTW/Fréchet ([US-24]), probe e palpites ([US-26]) — opera no referencial da sala.
- [RN04] Se o laboratório responder na pergunta B4 que a plataforma **não** é rotacionada, a rotação é fixada em 0° para todos os trials e a conversão vira identidade — mas a coluna e o caminho de código permanecem.
- [RN05] As saídas identificam explicitamente em qual referencial cada coluna está expressa.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — conversão entre referenciais**
  - **Dado que** dois trials do mesmo animal foram gravados com rotações diferentes (por exemplo, 0° e 90°),
  - **Quando** o pesquisador consulta a posição do buraco-alvo de cada trial no referencial da sala,
  - **Então** a posição da sala é **a mesma** nos dois trials, embora o índice do buraco seja diferente.

- **Cenário 2: Consistência da conversão de ida e volta**
  - **Dado que** um trial tem rotação registrada de R graus,
  - **Quando** um índice de buraco é convertido para posição da sala e de volta para índice,
  - **Então** o índice recuperado é idêntico ao original, para todos os N buracos.

- **Cenário 3: Tratamento de erro — rotação não informada**
  - **Dado que** um trial foi cadastrado sem valor em `trial.rotacao`,
  - **Quando** qualquer análise longitudinal é solicitada para esse trial,
  - **Então** o sistema recusa a análise e identifica o trial com rotação faltante, em vez de assumir 0°.

#### Tarefas
- [ ] Obter e registrar a resposta da pergunta B4 (rotação entre trials) — **portão G2**
- [ ] Adicionar a coluna `trial.rotacao` ao esquema SQLite, sem valor padrão silencioso
- [ ] Implementar a conversão índice de buraco → posição angular na sala
- [ ] Implementar a conversão inversa, posição na sala → índice de buraco
- [ ] Implementar a recusa de análise longitudinal para trial sem rotação registrada
- [ ] Implementar a identificação do referencial de cada coluna nas saídas
- [ ] Escrever teste de ida e volta da conversão para todos os N buracos
- [ ] Verificar a conversão em dois trials reais com rotações diferentes
- [ ] Registrar a resposta de B4 em `docs/definicoes-metricas.md`

#### Definição de Pronto (DoD Específica do Card)
- [ ] Coluna `trial.rotacao` no esquema SQLite, sem valor padrão silencioso
- [ ] Funções de conversão índice↔sala implementadas e testadas em ida e volta para todos os buracos
- [ ] Verificação executada em dois trials reais com rotações diferentes
- [ ] Referencial de cada coluna documentado nas saídas
- [ ] Resposta da pergunta B4 registrada em `docs/definicoes-metricas.md`

---

# Épico C — Rastreamento e pose

### [US-06] Anotação de quadros para treino do modelo de pose

- **Épico / Módulo:** Rastreamento e pose (`data/annotations/`, `docs/protocolo-anotacao.md`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 8 Pontos · 1 semana (anotação dos quadros não acelera com IA)
- **Sprint:** S1

#### Narrativa de Usuário
- **Como** equipe de desenvolvimento,
- **Queremos** anotar quadros marcando focinho, centro do corpo e base da cauda, com amostragem controlada,
- **Para que** exista um conjunto de treino representativo o bastante para o modelo de pose funcionar onde os eventos realmente acontecem.

#### Regras de Negócio & Escopo
- [RN01] Três pontos por animal, sempre na mesma ordem: **focinho, centro do corpo, base da cauda**.
- [RN02] A amostragem de quadros cobre obrigatoriamente três situações: animal no **centro** da plataforma, na **borda** e em **proximidade dos buracos** — esta última é onde a perda de pose é mais provável e mais cara.
- [RN03] A divisão treino/validação/teste é feita **por trial**, nunca por quadro sorteado, para evitar vazamento entre conjuntos.
- [RN04] Protocolo de amostragem, convenção dos pontos e divisão dos conjuntos ficam escritos em `docs/protocolo-anotacao.md`.
- [RN05] A anotação usa a interface do próprio SLEAP; nenhuma ferramenta de anotação própria será construída.
- [RN06] Quadros anotados podem subir para a nuvem de treino apenas se a pergunta D4 (restrição de uso e CEUA) tiver resposta explícita e favorável.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — conjunto anotado e dividido**
  - **Dado que** a equipe recebeu os 3 trials representativos de G1,
  - **Quando** conclui a rodada de anotação,
  - **Então** existe um conjunto anotado com os três pontos em todos os quadros selecionados e a divisão treino/validação/teste registrada em `docs/protocolo-anotacao.md`.

- **Cenário 2: Verificação de cobertura da amostragem**
  - **Dado que** o conjunto anotado está pronto,
  - **Quando** se contam os quadros por região da plataforma,
  - **Então** cada uma das três situações (centro, borda, proximidade de buraco) tem representação não nula e a proporção está documentada.

- **Cenário 3: Tratamento de erro — vazamento entre conjuntos**
  - **Dado que** um mesmo trial teve quadros em treino e em teste,
  - **Quando** a divisão é verificada,
  - **Então** a verificação falha e aponta o trial duplicado, exigindo nova divisão.

#### Tarefas
- [ ] Obter a resposta de D4 (restrição de uso e CEUA) antes de qualquer upload
- [ ] Definir a convenção dos três pontos e a ordem de marcação
- [ ] Definir a estratégia de amostragem por região (centro, borda, proximidade de buraco)
- [ ] Escrever `docs/protocolo-anotacao.md`
- [ ] Montar o projeto SLEAP e importar os quadros amostrados
- [ ] Anotar os quadros — atividade dividida entre a equipe, com meta por pessoa
- [ ] Implementar a divisão treino/validação/teste **por trial**
- [ ] Implementar a verificação automatizada de ausência de vazamento entre conjuntos
- [ ] Reportar a contagem de quadros anotados por região

#### Definição de Pronto (DoD Específica do Card)
- [ ] Projeto SLEAP de anotação criado, com os três pontos na convenção definida
- [ ] `docs/protocolo-anotacao.md` escrito e revisado
- [ ] Verificação automatizada de ausência de vazamento entre treino/validação/teste
- [ ] Contagem de quadros por região reportada
- [ ] Resposta de D4 confirmada antes de qualquer upload

---

### [US-07] Ambiente e treino do modelo de pose

- **Épico / Módulo:** Rastreamento e pose (`src/barnes/pose/`, `models/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias (treino é relógio de parede, não acelera com IA)
- **Sprint:** S2

#### Narrativa de Usuário
- **Como** equipe de desenvolvimento,
- **Queremos** treinar um modelo de pose para animal único a partir dos quadros anotados,
- **Para que** exista um modelo capaz de localizar focinho, centro e base da cauda sem intervenção humana.

#### Regras de Negócio & Escopo
- [RN01] Modelo treinado com SLEAP (alternativa: DeepLabCut). Ultralytics/YOLO-pose está fora por causa da licença AGPL.
- [RN02] Treino em GPU institucional, Kaggle ou Colab — nessa ordem de preferência, conforme resposta de D2.
- [RN03] Os pesos são versionados em `models/` (fora do Git) com identificador registrado na tabela `execucao`.
- [RN04] O acervo de vídeo **não** sobe para a nuvem; sobem apenas os quadros rotulados.
- [RN05] Os hiperparâmetros e a versão do conjunto de dados ficam registrados, para que o treino seja reproduzível.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — treino concluído**
  - **Dado que** o conjunto anotado de [US-06] está dividido em treino, validação e teste,
  - **Quando** o treino é executado,
  - **Então** os pesos são gerados e versionados em `models/` com identificador, e os hiperparâmetros ficam registrados.

- **Cenário 2: Reprodutibilidade do treino**
  - **Dado que** um modelo foi treinado há semanas,
  - **Quando** se consulta o registro do treino,
  - **Então** hiperparâmetros, versão do conjunto e ambiente são suficientes para repetir a execução.

- **Cenário 3: Tratamento de exceção — GPU indisponível**
  - **Dado que** não há GPU institucional disponível,
  - **Quando** o treino é planejado,
  - **Então** o fallback para Kaggle ou Colab é acionado e a escolha fica registrada, sem que o acervo de vídeo saia da infraestrutura do laboratório.

#### Tarefas
- [ ] Confirmar a disponibilidade de GPU institucional (pergunta D2) antes de recorrer a Kaggle ou Colab
- [ ] Preparar o ambiente de treino e o pacote de dados rotulados
- [ ] Treinar o modelo SLEAP e registrar os hiperparâmetros usados
- [ ] Versionar os pesos em `models/` com identificador registrável em `execucao`
- [ ] Registrar versão do conjunto de dados e ambiente, para reprodutibilidade

#### Definição de Pronto (DoD Específica do Card)
- [ ] Modelo treinado e pesos versionados em `models/` com identificador
- [ ] Configuração de treino reproduzível (parâmetros e versão de dados registrados)
- [ ] Nenhum vídeo enviado para a nuvem

---

### [US-08] Avaliação do modelo por região e inferência local

- **Épico / Módulo:** Rastreamento e pose (`src/barnes/pose/`, `models/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 3 Pontos · 1,5–2 dias
- **Sprint:** S2

#### Narrativa de Usuário
- **Como** equipe de desenvolvimento,
- **Queremos** medir o erro do modelo separadamente por região da plataforma e validar a inferência na máquina do laboratório,
- **Para que** saibamos se o modelo funciona onde os eventos realmente acontecem, e não apenas na média.

#### Regras de Negócio & Escopo
- [RN01] Critério de qualidade: **erro mediano de localização abaixo de meio corpo do animal** no conjunto de teste.
- [RN02] O desempenho é reportado **separadamente para quadros de centro, de borda e de proximidade de buraco** — a média global esconde exatamente a falha que importa.
- [RN03] Inferência roda **local**, na máquina do laboratório, sem rede.
- [RN04] O tempo de inferência por trial é medido e registrado, por ser requisito não-funcional da entrega.
- [RN05] Se o erro global passar mas o de borda reprovar, o card **não é aceito** — abre-se nova rodada de anotação enviesada para borda em [US-06].

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — modelo atinge o critério**
  - **Dado que** o modelo de [US-07] foi treinado,
  - **Quando** é avaliado no conjunto de teste,
  - **Então** o erro mediano de localização dos três pontos fica abaixo de meio corpo do animal.

- **Cenário 2: Desempenho segmentado por região**
  - **Dado que** o modelo foi avaliado,
  - **Quando** o relatório de avaliação é consultado,
  - **Então** ele traz o erro reportado separadamente para quadros de centro, de borda e de proximidade de buraco.

- **Cenário 3: Fluxo alternativo — critério não atingido em quadros de borda**
  - **Dado que** o erro global passa no critério mas o erro em quadros de borda não,
  - **Quando** o resultado é revisado,
  - **Então** o card não é aceito e é aberta nova rodada de anotação enviesada para borda, registrada no risco "perda de pose junto à borda".

- **Cenário 4: Inferência offline**
  - **Dado que** a máquina do laboratório está sem rede,
  - **Quando** um trial é processado,
  - **Então** a inferência roda normalmente e o tempo por trial é registrado.

#### Tarefas
- [ ] Avaliar o erro mediano de localização no conjunto de teste
- [ ] Segmentar a avaliação por região (centro, borda, proximidade de buraco)
- [ ] Validar a inferência local, sem rede, na máquina do laboratório
- [ ] Medir e registrar o tempo de inferência por trial
- [ ] Abrir nova rodada de anotação enviesada para borda, se o critério de borda reprovar

#### Definição de Pronto (DoD Específica do Card)
- [ ] Relatório de avaliação com erro global e por região
- [ ] Inferência validada na máquina do laboratório (sem rede)
- [ ] Tempo de inferência por trial medido e registrado

---

### [US-09] Série temporal de posição e orientação da cabeça

- **Épico / Módulo:** Rastreamento e pose (`src/barnes/pose/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 8 Pontos · 1 semana
- **Sprint:** S2

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** a série temporal de posição e orientação da cabeça do animal,
- **Para que** eu saiba para onde ele estava **olhando**, e não apenas por onde passou — que é o que separa "encontrar" de "passar perto".

#### Regras de Negócio & Escopo
- [RN01] Saída: uma linha por quadro com `(x, y, θ, t)` — posição em **cm**, orientação em **graus**, tempo em **segundos** desde o início do intervalo útil.
- [RN02] A orientação θ é derivada do eixo **centro do corpo → focinho**, e essa convenção fica documentada junto do dado.
- [RN03] A convenção angular (origem e sentido) é única em todo o sistema e coerente com a geometria de [US-04].
- [RN04] A série é persistida em `data/interim/*.parquet`, **um arquivo por trial**, e é a entrada de todo o Épico D.
- [RN05] Quadros sem pose válida aparecem na série marcados como ausentes, nunca preenchidos silenciosamente com o valor anterior — o preenchimento é responsabilidade de [US-10] e fica registrado.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — série gerada**
  - **Dado que** um trial foi processado com o modelo de pose,
  - **Quando** a série temporal é gerada,
  - **Então** o Parquet do trial contém uma linha por quadro do intervalo útil, com `x` e `y` em cm, `θ` em graus e `t` em segundos.

- **Cenário 2: Verificação da orientação**
  - **Dado que** um trecho de vídeo em que o animal atravessa a plataforma em linha reta e conhecida,
  - **Quando** se compara θ com a direção de deslocamento nesse trecho,
  - **Então** os valores concordam dentro da tolerância documentada, confirmando origem e sentido da convenção angular.

- **Cenário 3: Fluxo alternativo — quadro sem pose**
  - **Dado que** o modelo não detectou o focinho em um quadro,
  - **Quando** a série é gerada,
  - **Então** a linha correspondente existe com valores marcados como ausentes, sem repetir o quadro anterior.

#### Tarefas
- [ ] Fixar o esquema do Parquet de trajetória como contrato de dados entre módulos
- [ ] Comunicar o contrato às equipes de eventos, métricas e estratégia
- [ ] Implementar a inferência em lote sobre o trial já recortado
- [ ] Implementar a conversão de coordenadas px→cm usando a escala da montagem
- [ ] Implementar o cálculo de θ pelo eixo centro do corpo → focinho
- [ ] Fixar e documentar a convenção angular (origem e sentido), coerente com a geometria
- [ ] Implementar a marcação de quadro sem pose válida, sem preenchimento silencioso
- [ ] Escrever testes de conversão px→cm e de cálculo de θ
- [ ] Gerar e inspecionar a série para os 3 trials representativos

#### Definição de Pronto (DoD Específica do Card)
- [ ] Geração da série `(x, y, θ, t)` implementada em `pose/`
- [ ] Convenção angular documentada em `docs/definicoes-metricas.md`
- [ ] Esquema do Parquet de trajetória fixado como contrato de dados entre módulos
- [ ] Testes unitários de conversão px→cm e de cálculo de θ
- [ ] Série gerada para os 3 trials representativos

---

### [US-10] Suavização, interpolação e revisão de falhas de pose

- **Épico / Módulo:** Rastreamento e pose (`src/barnes/pose/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S2

#### Narrativa de Usuário
- **Como** operador,
- **Quero** que falhas de pose sejam suavizadas, interpoladas e sinalizadas, e poder revisar apenas os trechos marcados,
- **Para que** um trial inteiro não seja perdido por causa de alguns quadros ruins, nem aceito com lacunas que ninguém viu.

#### Regras de Negócio & Escopo
- [RN01] Lacunas **curtas** (até o limite configurado em `configs/`) são interpoladas automaticamente e marcadas como interpoladas na série.
- [RN02] Lacunas **longas** não são interpoladas: são sinalizadas para revisão humana.
- [RN03] O sistema reporta a **cobertura de pose** por trial — fração de quadros com os três pontos válidos. Critério de aceite do projeto: **≥ 0,98**.
- [RN04] A revisão permite navegação direta aos trechos sinalizados, sem varrer o vídeo inteiro.
- [RN05] Toda correção manual é registrada na tabela `execucao`, para que o número final seja auditável.
- [RN06] Trials abaixo do limiar de cobertura, mesmo após revisão, são marcados como de qualidade insuficiente e essa marcação acompanha o trial nas saídas.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — lacuna curta interpolada**
  - **Dado que** um trial tem uma lacuna de pose menor que o limite configurado,
  - **Quando** a série é pós-processada,
  - **Então** a lacuna é interpolada, as linhas resultantes ficam marcadas como interpoladas e nenhuma revisão é solicitada.

- **Cenário 2: Fluxo alternativo — lacuna longa sinalizada e revisada**
  - **Dado que** um trial tem uma lacuna maior que o limite,
  - **Quando** o operador abre a revisão,
  - **Então** o sistema o leva diretamente ao trecho sinalizado, permite a correção, e registra a intervenção na execução.

- **Cenário 3: Fluxo de exceção — cobertura abaixo do critério**
  - **Dado que** um trial ficou com cobertura de pose de 0,93 após a revisão,
  - **Quando** as métricas são exportadas,
  - **Então** o trial aparece nas saídas com a marcação de qualidade insuficiente e o valor da cobertura.

#### Tarefas
- [ ] Definir os limites de lacuna curta e de lacuna longa em `configs/`
- [ ] Implementar a suavização da série de pose
- [ ] Implementar a interpolação de lacunas curtas, com marcação das linhas interpoladas
- [ ] Implementar a sinalização de lacunas longas, sem interpolar
- [ ] Implementar o cálculo da cobertura de pose por trial
- [ ] Implementar a navegação direta aos trechos sinalizados na interface de revisão
- [ ] Implementar o registro das correções manuais na tabela `execucao`
- [ ] Implementar a marcação de trial com qualidade insuficiente, propagada às saídas
- [ ] Escrever testes para lacuna curta, lacuna longa e cobertura abaixo do critério

#### Definição de Pronto (DoD Específica do Card)
- [ ] Interpolação com limite configurável implementada
- [ ] Métrica de cobertura de pose calculada e persistida por trial
- [ ] Navegação direta a trechos sinalizados funcionando na interface de revisão
- [ ] Correções manuais registradas em `execucao`
- [ ] Testes cobrindo lacuna curta, lacuna longa e cobertura abaixo do critério

---

# Épico D — Eventos por buraco

### [US-11] Detecção do evento de descoberta (D) e persistência dos eventos

- **Épico / Módulo:** Eventos por buraco (`src/barnes/events/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S2

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** o instante em que o animal **encontra** cada buraco, definido por proximidade e orientação da cabeça,
- **Para que** eu possa separar percepção de comprometimento — medida que o cronômetro do observador não consegue produzir.

#### Regras de Negócio & Escopo
- [RN01] Um evento de descoberta ocorre no **primeiro quadro** em que **ambas** as condições são satisfeitas: distância do focinho ao buraco abaixo do limiar **e** ângulo entre a orientação da cabeça e a direção ao buraco abaixo do limiar angular.
- [RN02] Os dois limiares vêm de `configs/` (`barnes.yaml`), com valores acordados em **G3** e registrados em `docs/definicoes-metricas.md`. **Nenhum valor é constante no código.**
- [RN03] O evento é registrado uma única vez por buraco por trial — o primeiro encontro. Reaproximações posteriores não geram nova descoberta.
- [RN04] Os eventos são persistidos na tabela `evento_buraco`, camada intermediária entre trajetória e métrica: mudar um limiar recalcula eventos e métricas **sem reprocessar vídeo**.
- [RN05] A descoberta do **buraco-alvo** corresponde ao evento **D** do pipeline existente e alimenta `primary_latency` / `primary_distance` em [US-25].
- [RN06] **Card antecipado para o Sprint 2**, no mesmo sprint que a série de pose ([US-09], [US-10]) da qual depende. O acoplamento é deliberado: é aqui que se materializa o risco "definição operacional divergente", classificado como fatal e provável. Vale mais descobrir na semana 4 que a distinção encontrar/entrar não fecha do que na semana 6. Em contrapartida, o card **não pode começar antes de [US-09] entregar a série** — a ordenação dentro do sprint é obrigatória, não sugerida.
- [RN07] A validação contra a anotação manual **não** faz parte deste card: está em [US-12], no Sprint 3, porque depende da entrega da anotação pelo laboratório (D3).

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — descoberta detectada**
  - **Dado que** os limiares de distância e ângulo estão definidos em `barnes.yaml` conforme G3,
  - **Quando** o animal se aproxima de um buraco a menos que o limiar de distância **e** com a cabeça orientada dentro do limiar angular,
  - **Então** o sistema grava um evento de descoberta para aquele buraco, com carimbo de tempo do primeiro quadro que satisfez ambas as condições.

- **Cenário 2: Fluxo alternativo — passagem sem orientação**
  - **Dado que** o animal contorna a borda passando perto de vários buracos sem orientar a cabeça para nenhum,
  - **Quando** os eventos são calculados,
  - **Então** **nenhum** evento de descoberta é gerado para esses buracos.

- **Cenário 3: Recálculo sem reprocessamento de vídeo**
  - **Dado que** o laboratório revisou o limiar de distância,
  - **Quando** o valor é alterado em `barnes.yaml` e o recálculo é disparado,
  - **Então** os eventos e as métricas derivadas são recalculados a partir do Parquet, sem ler um único quadro de vídeo.

#### Tarefas
- [ ] Confirmar os limiares de distância e de ângulo saídos de **G3** (pergunta C1)
- [ ] Declarar os limiares em `barnes.yaml` e carregá-los como parâmetros
- [ ] Implementar o cálculo da distância focinho→buraco por quadro
- [ ] Implementar o cálculo do ângulo entre a orientação da cabeça e a direção ao buraco
- [ ] Implementar a regra de primeiro quadro que satisfaz ambas as condições
- [ ] Implementar o registro único por buraco por trial (ignorar reaproximações)
- [ ] Criar a tabela `evento_buraco` e implementar sua persistência
- [ ] Implementar o recálculo de eventos a partir do Parquet, sem acesso ao vídeo
- [ ] Escrever teste garantindo que o recálculo não abre nenhum arquivo de vídeo
- [ ] Registrar os limiares e sua origem em `docs/definicoes-metricas.md`

#### Definição de Pronto (DoD Específica do Card)
- [ ] Detecção de descoberta implementada com ambos os limiares parametrizados
- [ ] Tabela `evento_buraco` persistida e consultável
- [ ] Recálculo a partir do Parquet verificado por teste (sem acesso ao vídeo)
- [ ] Limiares e sua origem (G3) documentados em `docs/definicoes-metricas.md`

---

### [US-12] Calibração dos limiares de descoberta contra a anotação manual

- **Épico / Módulo:** Eventos por buraco (`src/barnes/events/`, `docs/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 3 Pontos · 1,5–2 dias (depende do laboratório, não acelera com IA)
- **Sprint:** S3

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** que os limiares de descoberta sejam calibrados contra a anotação de um observador treinado,
- **Para que** o número que o software chama de "encontrar" seja o mesmo que o laboratório chama de "encontrar".

#### Regras de Negócio & Escopo
- [RN01] Critério de aceite do projeto: diferença contra a anotação manual **≤ 0,5 s** por descoberta anotada.
- [RN02] A calibração ajusta os limiares em `barnes.yaml` — **nunca** o código de [US-11].
- [RN03] Cada rodada de ajuste é registrada, com os limiares testados e o erro resultante, para que a escolha final seja auditável.
- [RN04] O card depende da entrega da anotação manual pelo laboratório (**D3**) e é o motivo pelo qual essa entrega precisa de data marcada desde a semana 2.
- [RN05] Os limiares finais e a evidência da calibração vão para `docs/definicoes-metricas.md`, que é a base do aceite por escrito do PI (**G3**).

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — calibração converge**
  - **Dado que** um observador treinado anotou os tempos de descoberta de um trial de referência,
  - **Quando** os eventos automáticos são comparados com a anotação,
  - **Então** a diferença de tempo é **≤ 0,5 s** para cada descoberta anotada, e os limiares usados ficam registrados.

- **Cenário 2: Fluxo alternativo — calibração não converge**
  - **Dado que** nenhuma combinação de limiares atinge a tolerância,
  - **Quando** o resultado é revisado,
  - **Então** a divergência é levada ao PI como questão de definição operacional, e não tratada como defeito de software.

- **Cenário 3: Tratamento de exceção — anotação não entregue**
  - **Dado que** a anotação manual de D3 não chegou,
  - **Quando** o sprint é planejado,
  - **Então** o card é declarado bloqueado por dependência externa, e não é iniciado com anotação improvisada pelo próprio grupo.

#### Tarefas
- [ ] Cobrar e receber a anotação de eventos de D3, com data acordada
- [ ] Comparar os eventos automáticos com a anotação e medir a diferença
- [ ] Ajustar os limiares em `barnes.yaml` e reexecutar, registrando cada rodada
- [ ] Verificar a tolerância de 0,5 s no trial de referência
- [ ] Registrar limiares finais e evidência em `docs/definicoes-metricas.md`
- [ ] Levar os limiares acordados ao PI para o aceite por escrito de **G3**

#### Definição de Pronto (DoD Específica do Card)
- [ ] Comparação com anotação manual executada em trial de referência
- [ ] Tolerância de 0,5 s atingida, ou divergência escalada ao PI com registro
- [ ] Histórico das rodadas de calibração registrado
- [ ] `docs/definicoes-metricas.md` atualizado e submetido ao aceite do PI

---

### [US-13] Evento de entrada (E) — quando o animal *checa* fisicamente o buraco

- **Épico / Módulo:** Eventos por buraco (`src/barnes/events/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S3

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** o instante em que o animal **entra** ou checa fisicamente cada buraco,
- **Para que** eu complete o par com o tempo de descoberta e obtenha a hesitação entre perceber e agir.

#### Regras de Negócio & Escopo
- [RN01] Uma entrada ocorre quando o focinho permanece **dentro** da área do buraco por uma **duração mínima**; ambos os critérios (área e duração) são configuráveis em `configs/`.
- [RN02] A diferença **descoberta → entrada** (fase de decisão, D→E) é exportada como medida de hesitação, em tempo e em distância, alimentando `delta_latency` e `delta_distance` em [US-25].
- [RN03] Uma entrada sempre pressupõe uma descoberta anterior no mesmo buraco e no mesmo trial; entrada sem descoberta correspondente é inconsistência e deve ser sinalizada.
- [RN04] Critério de aceite do projeto: diferença contra a anotação manual **≤ 0,3 s**.
- [RN05] A entrada no **buraco-alvo** corresponde ao evento **E** e alimenta `total_latency` / `total_distance`.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — entrada registrada com hesitação**
  - **Dado que** o animal descobriu um buraco no instante t_D,
  - **Quando** ele mantém o focinho dentro da área do buraco pela duração mínima configurada, no instante t_E,
  - **Então** o sistema grava o evento de entrada em t_E e exporta a hesitação t_E − t_D.

- **Cenário 2: Fluxo alternativo — toque abaixo da duração mínima**
  - **Dado que** o focinho entra na área do buraco por tempo inferior à duração mínima,
  - **Quando** os eventos são calculados,
  - **Então** **nenhum** evento de entrada é gerado — permanece apenas a descoberta.

- **Cenário 3: Validação contra anotação manual**
  - **Dado que** um observador anotou os tempos de entrada de um trial de referência,
  - **Quando** os eventos automáticos são comparados,
  - **Então** a diferença é **≤ 0,3 s** para cada entrada anotada.

- **Cenário 4: Tratamento de inconsistência**
  - **Dado que** um evento de entrada foi gerado sem descoberta prévia no mesmo buraco,
  - **Quando** a consistência dos eventos é verificada,
  - **Então** o sistema sinaliza a inconsistência identificando trial e buraco.

#### Tarefas
- [ ] Confirmar os critérios de área e de duração mínima saídos de **G3** (pergunta C2)
- [ ] Declarar os critérios em `barnes.yaml`
- [ ] Implementar a detecção de focinho dentro da área do buraco
- [ ] Implementar o critério de duração mínima contínua
- [ ] Implementar o cálculo da hesitação D→E em tempo e em distância
- [ ] Implementar a verificação de consistência (entrada sem descoberta prévia)
- [ ] Comparar com a anotação manual e verificar a tolerância de 0,3 s
- [ ] Documentar o critério em `docs/definicoes-metricas.md`

#### Definição de Pronto (DoD Específica do Card)
- [ ] Detecção de entrada implementada com área e duração parametrizadas
- [ ] Hesitação D→E calculada em tempo e distância
- [ ] Verificação de consistência descoberta→entrada implementada
- [ ] Comparação com anotação manual executada
- [ ] Critérios documentados em `docs/definicoes-metricas.md`

---

### [US-14] Tempo de permanência (dwell) por buraco checado

- **Épico / Módulo:** Eventos por buraco (`src/barnes/events/`)
- **Prioridade Sugerida:** Média
- **Complexidade Estimada:** 2 Pontos · 1 dia
- **Sprint:** S3

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** o tempo de permanência do animal em cada buraco checado,
- **Para que** eu distinga uma checagem rápida de passagem de uma inspeção demorada e deliberada.

#### Regras de Negócio & Escopo
- [RN01] O dwell é medido **por evento**, em segundos, não agregado por buraco.
- [RN02] O critério de permanência (região considerada e continuidade) vem de `configs/`, coerente com a definição de entrada de [US-13].
- [RN03] Invariante de sanidade: a **soma de todos os dwells de um trial nunca excede a duração do intervalo útil** desse trial.
- [RN04] Dwells sobre quadros interpolados por [US-10] são marcados, para que uma inspeção medida sobre dados reconstruídos seja identificável.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — dwell por evento**
  - **Dado que** um trial tem cinco eventos de entrada registrados,
  - **Quando** as métricas de evento são calculadas,
  - **Então** cada um dos cinco eventos tem seu próprio dwell em segundos na tabela `evento_buraco`.

- **Cenário 2: Verificação do invariante**
  - **Dado que** os dwells de um trial de 300 s foram calculados,
  - **Quando** a soma dos dwells é verificada,
  - **Então** a soma é menor ou igual a 300 s, e o teste falha caso contrário.

- **Cenário 3: Fluxo alternativo — dwell sobre trecho interpolado**
  - **Dado que** parte do intervalo de permanência caiu sobre quadros interpolados,
  - **Quando** o dwell é calculado,
  - **Então** o evento fica marcado como apoiado em dados interpolados nas saídas.

#### Tarefas
- [ ] Definir o critério de permanência em `configs/`, coerente com a definição de entrada
- [ ] Implementar o cálculo de dwell por evento, em segundos
- [ ] Implementar a marcação de dwell apoiado em quadros interpolados
- [ ] Implementar a verificação do invariante soma(dwell) ≤ duração do intervalo útil
- [ ] Escrever o teste automatizado do invariante
- [ ] Conferir os valores manualmente em um trial de referência
- [ ] Documentar a coluna no dicionário de dados

#### Definição de Pronto (DoD Específica do Card)
- [ ] Cálculo de dwell por evento implementado
- [ ] Teste automatizado do invariante soma(dwell) ≤ duração do trial
- [ ] Marcação de dwell sobre trecho interpolado
- [ ] Coluna documentada no dicionário de dados
- [ ] Valores conferidos manualmente em um trial de referência

---

### [US-15] Sequência cronológica dos buracos checados

- **Épico / Módulo:** Eventos por buraco (`src/barnes/events/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 3 Pontos · 1,5–2 dias
- **Sprint:** S3

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** a ordem cronológica completa dos buracos checados, com carimbo de tempo,
- **Para que** eu possa auditar qualquer métrica derivada em vez de aceitar um número agregado que não consigo verificar.

#### Regras de Negócio & Escopo
- [RN01] A sequência é ordenada por tempo e exportável em formato tabular.
- [RN02] Cada item traz: ordem, índice do buraco, **posição no referencial da sala** ([US-05]), tempo de descoberta, tempo de entrada e dwell.
- [RN03] A sequência é a **entrada canônica** dos Épicos E (erros, [US-17]) e F (estratégia, [US-20]) — nenhum desses cálculos deve reler a trajetória.
- [RN04] Critério de aceite do projeto: concordância com a sequência anotada manualmente **≥ 0,95**.
- [RN05] A sequência é um contrato de dados entre módulos, fixado no Sprint 1 e alterado apenas com aviso à equipe.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — sequência exportada**
  - **Dado que** os eventos de um trial foram calculados,
  - **Quando** o pesquisador exporta a sequência de visitação,
  - **Então** ele recebe uma tabela ordenada por tempo com ordem, buraco, posição na sala, tempos de descoberta e entrada e dwell.

- **Cenário 2: Concordância com a anotação manual**
  - **Dado que** um observador anotou a sequência de buracos checados de um trial de referência,
  - **Quando** a sequência automática é comparada com a manual,
  - **Então** a concordância é **≥ 0,95**.

- **Cenário 3: Uso como fonte única**
  - **Dado que** as métricas de erro e a classificação de estratégia foram calculadas,
  - **Quando** se rastreia a origem dos dados usados,
  - **Então** ambas derivam exclusivamente da sequência persistida, sem novo acesso ao Parquet de trajetória.

#### Tarefas
- [ ] Fixar o esquema da sequência como contrato de dados dos Épicos E e F
- [ ] Comunicar o contrato aos responsáveis por métricas e por estratégia
- [ ] Implementar a montagem da sequência ordenada por tempo
- [ ] Incluir a posição no referencial da sala em cada item da sequência
- [ ] Implementar a exportação tabular da sequência
- [ ] Escrever teste de ordenação temporal estrita
- [ ] Comparar com a sequência anotada manualmente e verificar a concordância ≥ 0,95

#### Definição de Pronto (DoD Específica do Card)
- [ ] Sequência de visitação persistida e exportável
- [ ] Posição no referencial da sala incluída em cada item
- [ ] Comparação com anotação manual executada em trial de referência
- [ ] Contrato de dados documentado para os Épicos E e F
- [ ] Testes garantindo ordenação temporal estrita

---

# Épico E — Métricas por trial

### [US-16] Latência ao alvo com marcação de censura

- **Épico / Módulo:** Métricas por trial (`src/barnes/metrics/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S3

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** a latência até o buraco-alvo, com marcação explícita de censura quando o animal não o encontra,
- **Para que** a análise de sobrevivência receba os trials sem sucesso corretamente, em vez de descartá-los ou fingir sucesso no último segundo.

#### Regras de Negócio & Escopo
- [RN01] São reportadas **duas latências separadas**: latência de **descoberta** (S→D, `primary_latency`) e latência **total** até a entrada (S→E, `total_latency`).
- [RN02] Trials em que o animal não atinge o evento dentro do tempo limite são marcados como **censurados** (`primary_event = 0` ou `total_event = 0`) e **nunca descartados**.
- [RN03] O tempo limite do trial vem da resposta à pergunta B5 e fica em `configs/`.
- [RN04] Tempo zero é o evento S (início do intervalo útil de [US-03]).
- [RN05] Critério de aceite do projeto: diferença contra a cronometragem manual **≤ 1 s**.
- [RN06] As mesmas grandezas são calculadas também **em distância** (`primary_distance`, `total_distance`), porque o pipeline do laboratório modela ambas.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — animal encontra e entra no alvo**
  - **Dado que** o animal descobriu o alvo aos 45 s e entrou aos 58 s,
  - **Quando** as métricas do trial são calculadas,
  - **Então** `primary_latency = 45`, `total_latency = 58`, `primary_event = 1` e `total_event = 1`.

- **Cenário 2: Fluxo alternativo — animal descobre mas não entra**
  - **Dado que** o animal descobriu o alvo aos 90 s e não entrou até o tempo limite de 300 s,
  - **Quando** as métricas são calculadas,
  - **Então** `primary_latency = 90` com `primary_event = 1`, e `total_latency = 300` com `total_event = 0` (censurado), e o trial permanece no conjunto de dados.

- **Cenário 3: Fluxo alternativo — animal nunca encontra o alvo**
  - **Dado que** o animal não descobriu o alvo dentro do tempo limite,
  - **Quando** as métricas são calculadas,
  - **Então** ambos os eventos ficam censurados no tempo limite e o trial **não** é removido do conjunto.

- **Cenário 4: Validação contra cronometragem manual**
  - **Dado que** a latência de um trial de referência foi cronometrada manualmente,
  - **Quando** o valor automático é comparado,
  - **Então** a diferença é **≤ 1 s**.

#### Tarefas
- [ ] Confirmar com o laboratório o tempo limite do trial e o tratamento do insucesso (pergunta B5)
- [ ] Declarar o tempo limite em `configs/`
- [ ] Implementar `primary_latency` e `total_latency` a partir dos eventos D e E
- [ ] Implementar as versões em distância, `primary_distance` e `total_distance`
- [ ] Implementar a marcação de censura em `primary_event` e `total_event`
- [ ] Implementar o ancoramento do tempo zero no evento S
- [ ] Escrever teste garantindo que nenhum trial censurado é descartado
- [ ] Comparar com a cronometragem manual e verificar a tolerância de 1 s

#### Definição de Pronto (DoD Específica do Card)
- [ ] Latências de descoberta e total calculadas em tempo e em distância
- [ ] Colunas de censura preenchidas conforme convenção do pipeline existente (1 = evento, 0 = censurado)
- [ ] Teste automatizado garantindo que nenhum trial censurado é descartado
- [ ] Comparação com cronometragem manual executada
- [ ] Tempo limite parametrizado a partir da resposta de B5

---

### [US-17] Contagem e sequência de erros

- **Épico / Módulo:** Métricas por trial (`src/barnes/metrics/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 3 Pontos · 1,5–2 dias
- **Sprint:** S4

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** o número e a sequência de erros cometidos no trial,
- **Para que** eu avalie o desempenho do animal e alimente a classificação de estratégia de busca.

#### Regras de Negócio & Escopo
- [RN01] A definição de erro é **configurável** conforme a resposta à pergunta C3: qualquer buraco incorreto checado, ou apenas checagens acima de determinada duração.
- [RN02] O erro é derivado exclusivamente da sequência de [US-15], não da trajetória bruta.
- [RN03] São reportados: contagem total de erros, sequência ordenada dos buracos incorretos, e erros **até** a descoberta do alvo (subconjunto usado pela classificação de estratégia).
- [RN04] Critério de aceite do projeto: diferença absoluta contra a contagem manual **≤ 1 erro por trial**.
- [RN05] Trocar a definição de erro recalcula a métrica a partir da camada de eventos, sem reprocessar vídeo nem trajetória.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — contagem com a definição acordada**
  - **Dado que** a definição de erro em `configs/` é "qualquer buraco incorreto checado",
  - **Quando** um trial com 7 checagens, sendo 6 em buracos incorretos, é processado,
  - **Então** a contagem de erros é 6 e a sequência lista os 6 buracos em ordem cronológica.

- **Cenário 2: Fluxo alternativo — definição com duração mínima**
  - **Dado que** a definição é alterada para "checagem incorreta com dwell ≥ 0,5 s",
  - **Quando** o mesmo trial é recalculado,
  - **Então** a contagem cai para o subconjunto que satisfaz a duração, e o recálculo não acessa o vídeo.

- **Cenário 3: Validação contra a contagem manual**
  - **Dado que** um observador contou os erros de um trial de referência,
  - **Quando** a contagem automática é comparada,
  - **Então** a diferença absoluta é **≤ 1**.

#### Tarefas
- [ ] Confirmar a definição de erro usada pelo laboratório (pergunta C3)
- [ ] Declarar a definição como parâmetro em `configs/`
- [ ] Implementar a contagem de erros a partir da sequência de [US-15]
- [ ] Implementar a sequência ordenada dos buracos incorretos checados
- [ ] Implementar o recorte "erros até a descoberta do alvo", usado pela classificação de estratégia
- [ ] Escrever teste de recálculo sob nova definição, sem acesso ao vídeo
- [ ] Comparar com a contagem manual e verificar a tolerância de 1 erro
- [ ] Registrar a definição adotada em `docs/definicoes-metricas.md`

#### Definição de Pronto (DoD Específica do Card)
- [ ] Definição de erro parametrizada em `configs/`
- [ ] Contagem, sequência e erros-até-o-alvo implementados
- [ ] Recálculo sem acesso a vídeo verificado por teste
- [ ] Comparação com contagem manual executada
- [ ] Definição adotada registrada em `docs/definicoes-metricas.md`

---

### [US-18] Distância, velocidade média e velocidade por fase

- **Épico / Módulo:** Métricas por trial (`src/barnes/metrics/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S4

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** distância total, velocidade média e velocidade instantânea discriminadas por fase,
- **Para que** eu avalie a busca independentemente do tempo total e compare grupos como o pipeline atual já faz.

#### Regras de Negócio & Escopo
- [RN01] Distância em **cm** e velocidades em **cm/s**, sempre a partir da série calibrada de [US-09].
- [RN02] As velocidades são reportadas por fase, na convenção do pipeline existente: **primária** (S→D), **de decisão** (D→E) e **total** (S→E) — correspondendo a `primary_speed`, `decision_speed` e `total_speed`.
- [RN03] A série de velocidade instantânea é exportável quadro a quadro.
- [RN04] Trechos interpolados por [US-10] entram no cálculo mas a fração interpolada é reportada junto da métrica.
- [RN05] Critério de aceite do projeto: correlação com a medida manual de referência **r ≥ 0,95**.
- [RN06] Quando a fase de decisão não existe (animal descobriu mas não entrou), `decision_speed` é ausente — nunca zero.
- [RN07] O pipeline do laboratório modela tempo e distância simetricamente. Este card produz a metade em distância do par que [US-16] produz em tempo, e ambos alimentam as colunas de `trials.csv` em [US-25].

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — métricas por fase**
  - **Dado que** um trial tem eventos S, D e E registrados,
  - **Quando** as métricas de deslocamento são calculadas,
  - **Então** o sistema reporta distância total em cm e as três velocidades (primária, decisão, total) em cm/s.

- **Cenário 2: Correlação com a referência manual**
  - **Dado que** um conjunto de trials teve a distância medida manualmente,
  - **Quando** os valores automáticos são correlacionados com os manuais,
  - **Então** **r ≥ 0,95**.

- **Cenário 3: Fluxo alternativo — trial sem fase de decisão**
  - **Dado que** o animal descobriu o alvo mas não entrou,
  - **Quando** as métricas são calculadas,
  - **Então** `decision_speed` sai como ausente, e não como 0, para não enviesar as comparações entre grupos.

#### Tarefas
- [ ] Implementar a integração da distância percorrida a partir da série calibrada
- [ ] Implementar a segmentação da trajetória pelas fases S→D, D→E e S→E
- [ ] Implementar as velocidades médias por fase (`primary_speed`, `decision_speed`, `total_speed`)
- [ ] Implementar a série de velocidade instantânea e sua exportação
- [ ] Implementar o valor ausente quando a fase de decisão não existe
- [ ] Implementar o relato da fração interpolada junto da métrica
- [ ] Alinhar os nomes de coluna com o esquema de [US-25]
- [ ] Medir a correlação com a referência manual e verificar r ≥ 0,95

#### Definição de Pronto (DoD Específica do Card)
- [ ] Distância e velocidades por fase implementadas
- [ ] Série de velocidade instantânea exportável
- [ ] Correlação com referência manual calculada e ≥ 0,95
- [ ] Ausência (não zero) tratada e coberta por teste
- [ ] Colunas alinhadas com o esquema de [US-25]

---

### [US-19] Índice de eficiência de rota

- **Épico / Módulo:** Métricas por trial (`src/barnes/metrics/`)
- **Prioridade Sugerida:** Média
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S4

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** o índice de eficiência de rota do animal até o alvo,
- **Para que** eu tenha uma medida de qualidade da busca mais robusta que a latência bruta, que confunde lentidão com desorientação.

#### Regras de Negócio & Escopo
- [RN01] O índice é a razão entre a **distância percorrida** até o alvo e a **distância mínima** do ponto de soltura ao alvo.
- [RN02] O **ponto de soltura é obtido por trial**, a partir da trajetória, e não fixado por suposição — o protocolo pode variar (pergunta B3).
- [RN03] O índice só é definido para trials em que o alvo foi alcançado; em trials censurados sai como ausente.
- [RN04] O índice é reportado junto do ponto de soltura detectado, para auditoria.
- [RN05] Valor mínimo teórico é 1,0 (rota ideal); valores abaixo de 1,0 indicam erro de cálculo e devem falhar a validação.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — rota direta**
  - **Dado que** um animal foi solto no centro e seguiu praticamente em linha reta até o alvo,
  - **Quando** o índice é calculado,
  - **Então** o valor fica próximo de 1,0 e o ponto de soltura detectado coincide com o centro.

- **Cenário 2: Fluxo alternativo — busca por tigmotaxia**
  - **Dado que** o animal contornou a borda antes de chegar ao alvo,
  - **Quando** o índice é calculado,
  - **Então** o valor é substancialmente maior que 1,0, refletindo o excesso de percurso.

- **Cenário 3: Tratamento de exceção — trial censurado**
  - **Dado que** o animal não alcançou o alvo,
  - **Quando** o índice é calculado,
  - **Então** ele sai como ausente, e não como um valor arbitrário.

- **Cenário 4: Validação de sanidade**
  - **Dado que** qualquer trial processado,
  - **Quando** o índice é verificado,
  - **Então** ele nunca é menor que 1,0; caso seja, o teste falha.

#### Tarefas
- [ ] Confirmar o protocolo de soltura do laboratório (pergunta B3)
- [ ] Implementar a detecção do ponto de soltura por trial, a partir da trajetória
- [ ] Implementar o cálculo da distância mínima do ponto de soltura ao alvo
- [ ] Implementar a razão distância percorrida / distância mínima
- [ ] Implementar o valor ausente do índice em trials censurados
- [ ] Implementar a exportação do ponto de soltura detectado junto da métrica
- [ ] Escrever o teste de sanidade índice ≥ 1,0
- [ ] Validar em um trial de rota direta e um de tigmotaxia

#### Definição de Pronto (DoD Específica do Card)
- [ ] Detecção do ponto de soltura por trial implementada
- [ ] Índice calculado, com ausência em trials censurados
- [ ] Teste de sanidade (índice ≥ 1,0) automatizado
- [ ] Ponto de soltura detectado exportado junto da métrica
- [ ] Comportamento validado em um trial de rota direta e um de tigmotaxia

---

# Épico F — Estratégia e aleatoriedade

### [US-20] Entropia da trajetória e classificação da estratégia de busca

- **Épico / Módulo:** Estratégia (`src/barnes/strategy/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 8 Pontos · 1 semana
- **Sprint:** S4

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** um índice de entropia da trajetória e a classificação da estratégia em aleatória, serial ou espacial,
- **Para que** eu quantifique a migração do padrão de busca ao longo das sessões, que é a evidência de aprendizado espacial.

#### Regras de Negócio & Escopo
- [RN01] A classificação é feita por **regra explícita e documentada**, não por modelo de aprendizado de máquina — com poucas dezenas de trials rotulados, um modelo treinado não generaliza e não é auditável perante a banca.
- [RN02] A regra combina três sinais: número de **cruzamentos do centro** da plataforma, **adjacência angular** dos buracos checados em sequência, e **erros até o alvo** ([US-17]).
- [RN03] **Todos** os limiares da regra ficam em `barnes.yaml`, ajustáveis sem alterar código.
- [RN04] A regra deve reproduzir o critério que o observador do laboratório já usa (pergunta C4); se o laboratório não tiver critério escrito, ele é definido em G3 antes deste card ser aceito.
- [RN05] A classificação opera sobre a sequência de [US-15] no **referencial da sala**, para que a adjacência angular seja comparável entre trials rotacionados.
- [RN06] Cada trial classificado registra também os valores dos três sinais, para que a decisão da regra seja inspecionável caso a caso.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — estratégia serial**
  - **Dado que** um trial em que o animal checou buracos angularmente adjacentes em sequência, sem cruzar o centro,
  - **Quando** a classificação é executada,
  - **Então** o trial é classificado como **serial** e os três sinais que levaram a essa decisão são registrados.

- **Cenário 2: Fluxo alternativo — estratégia espacial**
  - **Dado que** um trial em que o animal foi diretamente ao alvo com poucos erros e cruzando o centro,
  - **Quando** a classificação é executada,
  - **Então** o trial é classificado como **espacial**.

- **Cenário 3: Fluxo alternativo — estratégia aleatória**
  - **Dado que** um trial com muitos cruzamentos do centro, buracos checados sem adjacência e muitos erros,
  - **Quando** a classificação é executada,
  - **Então** o trial é classificado como **aleatória** e a entropia da trajetória é alta em relação aos demais trials do mesmo animal.

- **Cenário 4: Ajuste de limiar sem alteração de código**
  - **Dado que** o critério do observador foi refinado após revisão,
  - **Quando** os limiares em `barnes.yaml` são alterados e a classificação é reexecutada,
  - **Então** a nova classificação é produzida sem nenhuma alteração no código-fonte.

#### Tarefas
- [ ] Levantar com o observador o critério atual de classificação das três estratégias (pergunta C4)
- [ ] Implementar o índice de entropia da trajetória
- [ ] Implementar a contagem de cruzamentos do centro da plataforma
- [ ] Implementar a medida de adjacência angular dos buracos checados em sequência
- [ ] Implementar a regra de classificação combinando os três sinais
- [ ] Declarar todos os limiares da regra em `barnes.yaml`
- [ ] Garantir que a classificação opera sobre a sequência no referencial da sala
- [ ] Implementar o registro dos três sinais por trial, para auditoria caso a caso
- [ ] Escrever a regra completa em `docs/definicoes-metricas.md`
- [ ] Validar a classificação em um trial de cada categoria

#### Definição de Pronto (DoD Específica do Card)
- [ ] Índice de entropia da trajetória implementado e documentado
- [ ] Regra de classificação implementada com os três sinais parametrizados
- [ ] Sinais registrados por trial para auditoria caso a caso
- [ ] Classificação executada no referencial da sala
- [ ] Regra escrita em `docs/definicoes-metricas.md`, incluindo a origem do critério (C4)

---

### [US-21] Concordância da classificação automática com o observador (kappa)

- **Épico / Módulo:** Estratégia — validação (`src/barnes/strategy/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 8 Pontos · 1 semana
- **Sprint:** S4

#### Narrativa de Usuário
- **Como** equipe de desenvolvimento,
- **Queremos** comparar a classificação automática com a do observador treinado usando kappa de Cohen,
- **Para que** possamos provar, com número, que a regra reproduz o julgamento humano — e não apenas produz rótulos plausíveis.

#### Regras de Negócio & Escopo
- [RN01] O kappa de Cohen é calculado sobre a amostra de trials classificada manualmente na atividade D3.
- [RN02] Além do kappa global, é reportada a **matriz de confusão por categoria** (aleatória, serial, espacial) — um kappa aceitável pode esconder uma categoria sistematicamente errada.
- [RN03] Critério de aceite do projeto: **kappa ≥ 0,70**.
- [RN04] Se o kappa ficar abaixo do critério, os limiares da regra de [US-20] são ajustados e a avaliação **reexecutada**, com o histórico das rodadas registrado.
- [RN05] O ajuste dos limiares usa apenas a amostra de calibração; a reavaliação final não pode ser feita sobre os mesmos trials usados para ajustar, sob pena de kappa otimista.
- [RN06] Este card é executado no **Sprint 4**, e não no 5, deliberadamente: é preciso sobrar tempo para ajustar a regra se ela não concordar.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — concordância atingida**
  - **Dado que** o observador classificou a amostra de trials de D3,
  - **Quando** o kappa de Cohen é calculado contra a classificação automática,
  - **Então** o kappa é **≥ 0,70** e a matriz de confusão por categoria é gerada.

- **Cenário 2: Fluxo alternativo — concordância abaixo do critério**
  - **Dado que** o kappa calculado foi 0,52,
  - **Quando** o resultado é revisado,
  - **Então** o card não é aceito, os limiares da regra são ajustados sobre a amostra de calibração e uma nova rodada de avaliação é registrada.

- **Cenário 3: Prevenção de otimismo na avaliação**
  - **Dado que** os limiares foram ajustados usando um subconjunto da amostra anotada,
  - **Quando** o kappa final é reportado,
  - **Então** ele é calculado sobre trials que **não** participaram do ajuste, e isso está declarado no relatório.

#### Tarefas
- [ ] Cobrar e receber a anotação de estratégia de **D3**, com data acordada
- [ ] Separar a amostra anotada em subconjunto de calibração e de avaliação
- [ ] Implementar o cálculo de kappa de Cohen com scikit-learn
- [ ] Implementar a matriz de confusão por categoria
- [ ] Executar a primeira rodada de avaliação
- [ ] Ajustar os limiares de [US-20] sobre o subconjunto de calibração, se o kappa reprovar
- [ ] Reavaliar sobre o subconjunto de avaliação e registrar o histórico das rodadas
- [ ] Declarar no relatório que a avaliação final não usou trials de calibração
- [ ] Incorporar o resultado ao relatório de validação de [US-29]

#### Definição de Pronto (DoD Específica do Card)
- [ ] Cálculo de kappa de Cohen implementado com scikit-learn
- [ ] Matriz de confusão por categoria gerada
- [ ] Separação entre trials de calibração e de avaliação implementada e declarada
- [ ] Histórico de rodadas de ajuste registrado
- [ ] Resultado incorporado ao relatório de validação de [US-29]

---

# Épico G — Análise longitudinal e estatística

### [US-22] Curvas de aprendizado por sessão

- **Épico / Módulo:** Longitudinal (`src/barnes/longitudinal/`, `report/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 3 Pontos · 1,5–2 dias
- **Sprint:** S4

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** curvas de aprendizado de latência, erros, distância e entropia por número da sessão,
- **Para que** eu visualize a evolução de cada animal e do grupo ao longo do treinamento.

#### Regras de Negócio & Escopo
- [RN01] Uma curva **por animal** e uma curva **agregada por sessão**, esta última com medida de dispersão.
- [RN02] As quatro métricas de eixo Y: latência, erros, distância e entropia.
- [RN03] Os dados vêm **exclusivamente do banco**, nunca do vídeo — regerar uma curva leva segundos e não reprocessa um único quadro.
- [RN04] Trials censurados ([US-16]) são identificados na curva, não misturados silenciosamente com os bem-sucedidos.
- [RN05] Cada figura identifica a execução (modelo, limiares, commit) que produziu os dados.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — curvas geradas**
  - **Dado que** o banco contém trials de vários animais em várias sessões,
  - **Quando** o pesquisador solicita as curvas de aprendizado,
  - **Então** são geradas curvas por animal e curvas agregadas por sessão, com dispersão, para latência, erros, distância e entropia.

- **Cenário 2: Independência do vídeo**
  - **Dado que** os vídeos de `data/raw/` estão indisponíveis,
  - **Quando** as curvas são regeradas,
  - **Então** elas são produzidas normalmente a partir do banco.

- **Cenário 3: Tratamento de censura na visualização**
  - **Dado que** algumas sessões contêm trials censurados,
  - **Quando** a curva agregada é gerada,
  - **Então** os trials censurados aparecem identificados na figura ou na legenda, e não como valores completos.

#### Tarefas
- [ ] Implementar as consultas ao banco para latência, erros, distância e entropia por sessão
- [ ] Implementar a curva por animal
- [ ] Implementar a curva agregada por sessão, com medida de dispersão
- [ ] Implementar a identificação dos trials censurados na figura ou na legenda
- [ ] Implementar a impressão da identificação da execução em cada figura
- [ ] Escrever teste que gera as curvas sem nenhum acesso a `data/raw/`
- [ ] Exportar as figuras em formato reaproveitável pela análise do laboratório

#### Definição de Pronto (DoD Específica do Card)
- [ ] Curvas por animal e agregadas implementadas com Matplotlib/seaborn
- [ ] Leitura exclusivamente do banco, verificada por teste sem acesso a `data/raw/`
- [ ] Trials censurados identificados nas figuras
- [ ] Identificação da execução impressa em cada figura
- [ ] Figuras exportadas em formato utilizável pelo documento executável do laboratório

---

### [US-23] Teste de distribuição de estratégias entre sessões

- **Épico / Módulo:** Estatística (`src/barnes/stats/`)
- **Prioridade Sugerida:** Média
- **Complexidade Estimada:** 2 Pontos · 1 dia
- **Sprint:** S5

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** um teste qui-quadrado — ou exato de Fisher em amostra pequena — sobre a distribuição de estratégias entre sessões,
- **Para que** eu saiba se o padrão de busca realmente muda com o treinamento, em vez de apenas parecer mudar no gráfico.

#### Regras de Negócio & Escopo
- [RN01] O sistema monta a **tabela de contingência sessão × estratégia** a partir das classificações de [US-20].
- [RN02] A escolha entre qui-quadrado e exato de Fisher é feita **automaticamente pelo tamanho das células** (regra das frequências esperadas), e o teste escolhido é **registrado junto do resultado**.
- [RN03] São reportados: tabela de contingência, teste aplicado, estatística, valor-p e a justificativa da escolha do teste.
- [RN04] O mesmo procedimento pode ser aplicado a grupo × estratégia, se houver grupo experimental (pergunta B6).
- [RN05] Entrega-se o teste, não a significância. O grupo controla o pipeline, não o resultado biológico: um teste não significativo é um resultado válido e não caracteriza falha do software.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — amostra suficiente**
  - **Dado que** todas as frequências esperadas da tabela de contingência são adequadas ao qui-quadrado,
  - **Quando** o teste é executado,
  - **Então** o sistema aplica qui-quadrado e reporta tabela, estatística, valor-p e a justificativa da escolha.

- **Cenário 2: Fluxo alternativo — amostra pequena**
  - **Dado que** alguma célula tem frequência esperada abaixo do limite,
  - **Quando** o teste é executado,
  - **Então** o sistema aplica o exato de Fisher, reporta o resultado e registra explicitamente por que trocou de teste.

- **Cenário 3: Tratamento de exceção — categoria ausente**
  - **Dado que** nenhuma sessão apresentou a estratégia "espacial",
  - **Quando** a tabela é montada,
  - **Então** a categoria aparece com zeros e o relatório sinaliza a ausência, em vez de omitir a coluna silenciosamente.

#### Tarefas
- [ ] Confirmar a existência de grupo experimental além do controle (pergunta B6)
- [ ] Implementar a montagem da tabela de contingência sessão × estratégia a partir do banco
- [ ] Implementar a regra de seleção entre qui-quadrado e Fisher pelas frequências esperadas
- [ ] Implementar o registro da justificativa da escolha junto do resultado
- [ ] Implementar o relato de estatística e valor-p
- [ ] Implementar a sinalização de categoria de estratégia ausente
- [ ] Estender o procedimento à tabela grupo × estratégia, se houver grupo experimental
- [ ] Escrever testes cobrindo os dois caminhos de seleção de teste

#### Definição de Pronto (DoD Específica do Card)
- [ ] Tabela de contingência gerada a partir do banco
- [ ] Seleção automática entre qui-quadrado e Fisher implementada, com registro da justificativa
- [ ] Testes unitários cobrindo os dois caminhos de seleção
- [ ] Resultado exportado junto das demais saídas estatísticas
- [ ] Nenhuma dependência GPL introduzida

---

### [US-24] Similaridade entre trajetórias por DTW ou Fréchet

- **Épico / Módulo:** Longitudinal (`src/barnes/longitudinal/`)
- **Prioridade Sugerida:** Média
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S5

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** a distância DTW ou de Fréchet entre trials consecutivos do mesmo animal,
- **Para que** eu quantifique a estabilização do padrão de busca — a evidência de que a rota deixou de ser exploratória e virou rotina.

#### Regras de Negócio & Escopo
- [RN01] As trajetórias são **reamostradas** e colocadas no **referencial da sala** ([US-05]) antes de qualquer comparação; comparar trajetórias em referenciais diferentes produz números sem significado.
- [RN02] A distância é calculada por par de trials **consecutivos do mesmo animal**, e a série resultante é plotada ao longo das sessões.
- [RN03] A métrica escolhida (DTW ou Fréchet) e seus parâmetros ficam em `configs/` e são registrados junto do resultado.
- [RN04] Trajetórias com cobertura de pose insuficiente ([US-10]) são excluídas da comparação, e a exclusão é reportada.
- [RN05] **Contribuição protegida.** É a opção 1 recomendada na seção 8 do `definicao-projeto.md`: entre as duas análises avançadas, o DTW é a mais definida, tem biblioteca pronta e produz a figura mais forte para a defesa. Com a estatística redundante removida do Sprint 5, ele deixou de competir por espaço com validação e empacotamento.
- [RN06] A contrapartida está declarada: **[US-26] é o único candidato a corte** restante, e a decisão sobre ele é tomada no planejamento do Sprint 4 com a velocidade real dos três sprints anteriores em mãos — não na semana 10.
- [RN07] Este card depende de [US-05] (referencial da sala), entregue no Sprint 1, e das trajetórias do Sprint 2 — ambas disponíveis há vários sprints quando ele é executado.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — série de similaridade**
  - **Dado que** um animal tem trials em várias sessões consecutivas,
  - **Quando** a similaridade é calculada,
  - **Então** o sistema produz uma distância por par consecutivo e uma curva dessa distância ao longo das sessões.

- **Cenário 2: Normalização obrigatória**
  - **Dado que** dois trials consecutivos foram gravados com rotações diferentes da plataforma,
  - **Quando** a distância é calculada,
  - **Então** as trajetórias são convertidas ao referencial da sala antes da comparação, e o resultado é idêntico ao obtido se as rotações fossem iguais e as rotas espacialmente idênticas.

- **Cenário 3: Tratamento de exceção — trajetória de baixa qualidade**
  - **Dado que** um dos trials do par tem cobertura de pose abaixo do critério,
  - **Quando** a comparação é solicitada,
  - **Então** o par é excluído e a exclusão aparece no relatório com o motivo.

#### Tarefas
- [ ] Escolher a métrica (DTW ou Fréchet) e a biblioteca, e declarar a escolha em `configs/`
- [ ] Implementar a reamostragem das trajetórias para comprimento comparável
- [ ] Implementar a conversão ao referencial da sala antes de qualquer comparação
- [ ] Implementar a distância entre pares de trials consecutivos do mesmo animal
- [ ] Implementar a exclusão de trajetórias com cobertura de pose insuficiente, com relato do motivo
- [ ] Implementar a curva de similaridade ao longo das sessões
- [ ] Escrever teste verificando invariância do resultado à rotação da plataforma
- [ ] Registrar na ata do planejamento do S4 a decisão de proteger esta análise

#### Definição de Pronto (DoD Específica do Card)
- [ ] Reamostragem e conversão ao referencial da sala implementadas antes da métrica
- [ ] Distância entre pares consecutivos implementada com tslearn/dtaidistance ou similaritymeasures
- [ ] Curva de similaridade ao longo das sessões gerada
- [ ] Exclusões por qualidade reportadas
- [ ] Decisão de manter/antecipar/cortar registrada na ata do planejamento do Sprint 4

---

# Épico H — Probe, palpites e relatórios

### [US-25] Exportação compatível com `trials.csv` e `probes.csv`

- **Épico / Módulo:** Relatórios e integração (`src/barnes/report/`, `db/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 8 Pontos · 1 semana
- **Sprint:** S5

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** exportar as métricas exatamente no formato de `trials.csv` e `probes.csv` já usados pelo laboratório,
- **Para que** o código de análise estatística existente rode sobre os dados automáticos **sem nenhuma alteração**.

#### Regras de Negócio & Escopo
- [RN01] O esquema de saída reproduz o do laboratório: `animal`, `group`, `day`, `trial`, `primary_latency`, `primary_distance`, `primary_event`, `delta_latency`, `delta_distance`, `total_latency`, `total_distance`, `total_event`.
- [RN02] Nomes de coluna, ordem, unidades e codificação de censura (1 = evento observado, 0 = censurado) seguem o padrão existente, sem adaptação do lado do laboratório.
- [RN03] O `barnes_maze.py` atual deve **carregar e processar o CSV gerado sem edição de código** — este é o teste de aceitação do card.
- [RN04] Colunas adicionais produzidas por este projeto (estratégia, entropia, eficiência de rota, cobertura de pose, identificação da execução) vão em **arquivo complementar** ou em colunas ao final, sem quebrar a leitura do arquivo pelo pipeline existente.
- [RN05] Cada linha exportada carrega a identificação da execução ([US-27]), para que se saiba qual modelo e quais limiares produziram aquele número.
- [RN06] São gerados um CSV por trial e um consolidado por estudo; o dicionário de colunas fica no manual.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — pipeline existente roda sem alteração**
  - **Dado que** um conjunto de trials foi processado automaticamente,
  - **Quando** o `trials.csv` gerado é carregado pelo `barnes_maze.py` sem qualquer edição no código do laboratório,
  - **Então** os modelos de Cox são ajustados normalmente e produzem resultados.

- **Cenário 2: Validação cruzada contra a anotação manual**
  - **Dado que** existe um `trials.csv` produzido por anotação manual para o mesmo conjunto,
  - **Quando** os dois arquivos são processados pelo mesmo código de análise,
  - **Então** os hazard ratios obtidos são compatíveis, e a comparação fica registrada como evidência de validação.

- **Cenário 3: Tratamento de erro — coluna faltante ou fora de esquema**
  - **Dado que** alguma métrica obrigatória não pôde ser calculada para um trial,
  - **Quando** a exportação é executada,
  - **Então** a coluna existe com valor ausente explícito no formato esperado pelo pipeline, e o trial é listado no relatório de pendências — o arquivo nunca é gerado com coluna faltante.

#### Tarefas
- [ ] Obter do laboratório um `trials.csv` e um `probes.csv` reais, como referência de esquema
- [ ] Implementar o exportador com nomes, ordem, unidades e codificação de censura idênticos
- [ ] Implementar o CSV por trial e o consolidado por estudo
- [ ] Implementar as colunas complementares sem quebrar a leitura pelo pipeline existente
- [ ] Implementar a identificação da execução em cada linha
- [ ] Implementar o valor ausente explícito e o relatório de pendências por trial
- [ ] Executar o `barnes_maze.py` sobre a saída automática, sem alteração, e verificar
- [ ] Comparar os hazard ratios com os obtidos da anotação manual e registrar
- [ ] Escrever o dicionário de colunas em `docs/manual-usuario.md`

#### Definição de Pronto (DoD Específica do Card)
- [ ] Exportador com o esquema exato de `trials.csv` e `probes.csv` implementado
- [ ] Execução do `barnes_maze.py` sobre a saída automática, sem alteração, verificada
- [ ] CSV por trial e consolidado gerados
- [ ] Identificação da execução presente em cada linha
- [ ] Dicionário de colunas escrito em `docs/manual-usuario.md`

---

### [US-26] Análise do probe trial e investigação de palpites

- **Épico / Módulo:** Longitudinal (`src/barnes/longitudinal/`)
- **Prioridade Sugerida:** Média
- **Complexidade Estimada:** 8 Pontos · 1 semana
- **Sprint:** S5

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** a análise do probe trial e a investigação de palpites por experiência prévia,
- **Para que** eu evidencie memória consolidada em vez de sorte — distinguindo o animal que lembra do animal que acerta por acaso.

#### Regras de Negócio & Escopo
- [RN01] No probe, o sistema mede **tempo e número de checagens na região do antigo alvo**, comparados com as demais regiões da plataforma.
- [RN02] A análise de palpites correlaciona a **ordem dos buracos checados** no probe com os **alvos de trials anteriores** do mesmo animal — se o animal checa primeiro alvos antigos, isso é experiência prévia, não memória do alvo atual.
- [RN03] Toda a análise ocorre no **referencial da sala** ([US-05]).
- [RN04] O comportamento do probe no laboratório (alvo fechado, removido, plataforma limpa) vem da resposta à pergunta B7 e define o que é "buscar na região correta".
- [RN05] A saída de probe segue o esquema `probes.csv` de [US-25].
- [RN06] **Único card em risco declarado do backlog.** Com [US-24] antecipado para o Sprint 4, este passou a ser o candidato isolado a corte. A decisão é tomada no planejamento do Sprint 4, com a velocidade real dos três sprints anteriores medida. Se for cortado, entra na proposta como trabalho futuro **desde já** — a pior saída é mantê-lo no papel e chegar à semana 10 com ele pela metade.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — preferência pela região do alvo**
  - **Dado que** um probe trial foi processado,
  - **Quando** a análise é executada,
  - **Então** o sistema reporta tempo e número de checagens na região do antigo alvo e nas demais regiões, permitindo a comparação.

- **Cenário 2: Fluxo principal — análise de palpites**
  - **Dado que** o animal participou de sessões anteriores com alvos em posições diferentes,
  - **Quando** a análise de palpites é executada,
  - **Então** o sistema reporta a correlação entre a ordem de checagem no probe e as posições de alvos anteriores, no referencial da sala.

- **Cenário 3: Tratamento de exceção — histórico insuficiente**
  - **Dado que** o animal não tem trials anteriores com alvos em posições distintas,
  - **Quando** a análise de palpites é solicitada,
  - **Então** o sistema informa que não há histórico suficiente e não produz uma correlação sem base.

#### Tarefas
- [ ] Confirmar o protocolo de probe do laboratório (pergunta B7): alvo fechado, removido ou plataforma limpa
- [ ] Implementar a definição da região do antigo alvo conforme esse protocolo
- [ ] Implementar a medida de tempo e de número de checagens por região no probe
- [ ] Implementar o histórico de alvos anteriores por animal, no referencial da sala
- [ ] Implementar a correlação entre a ordem de checagem no probe e os alvos anteriores
- [ ] Implementar o tratamento de histórico insuficiente, sem produzir correlação sem base
- [ ] Implementar a saída no esquema `probes.csv`
- [ ] Registrar na ata do planejamento do S4 a decisão de manter ou cortar este card

#### Definição de Pronto (DoD Específica do Card)
- [ ] Métricas de região do antigo alvo implementadas conforme resposta de B7
- [ ] Correlação de palpites com alvos anteriores implementada
- [ ] Análise executada no referencial da sala
- [ ] Saída no esquema `probes.csv`
- [ ] Decisão de manter/cortar registrada na ata do planejamento do Sprint 4

---

# Épico I — Qualidade, validação e entrega

### [US-27] Proveniência das execuções e catálogo de trials

- **Épico / Módulo:** Qualidade e reprodutibilidade (`src/barnes/db/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S2

#### Narrativa de Usuário
- **Como** pesquisador,
- **Quero** que cada execução registre modelo, limiares, parâmetros e commit, e poder ver o catálogo dos trials processados,
- **Para que** eu consiga reproduzir e defender um resultado meses depois, quando ninguém lembrar da configuração usada.

#### Regras de Negócio & Escopo
- [RN01] A tabela `execucao` é preenchida **automaticamente** a cada processamento: identificador do modelo de pose, limiares operacionais vigentes, parâmetros, commit do código e data.
- [RN02] Nenhuma métrica é gravada sem vínculo a uma execução — métrica órfã é erro de esquema.
- [RN03] O catálogo lista trial, animal, sessão, situação de processamento e cobertura de pose.
- [RN04] O **hash do arquivo** de vídeo ([US-01]) detecta arquivo movido, renomeado ou alterado, sinalizando a divergência em vez de reprocessar silenciosamente.
- [RN05] O commit registrado deve identificar estado sujo do repositório quando houver alterações não commitadas no momento da execução.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — execução registrada**
  - **Dado que** um trial é processado,
  - **Quando** a execução termina,
  - **Então** uma linha em `execucao` registra modelo, limiares, parâmetros, commit e data, e todas as métricas geradas apontam para ela.

- **Cenário 2: Reprodução de um resultado antigo**
  - **Dado que** um resultado foi produzido há três meses,
  - **Quando** o pesquisador consulta a execução correspondente,
  - **Então** ele obtém o modelo, os limiares e o commit exatos usados, suficientes para reprocessar.

- **Cenário 3: Detecção de arquivo alterado**
  - **Dado que** um vídeo já catalogado foi movido ou substituído,
  - **Quando** o catálogo é consultado ou o trial reprocessado,
  - **Então** o sistema sinaliza a divergência de hash, identificando o trial afetado.

- **Cenário 4: Execução com repositório sujo**
  - **Dado que** existem alterações não commitadas no momento do processamento,
  - **Quando** a execução é registrada,
  - **Então** o registro marca o estado como sujo, para que o resultado não seja tomado como reproduzível.

#### Tarefas
- [ ] Modelar as tabelas do esquema SQLite: `animal`, `montagem`, `sessao`, `trial`, `evento_buraco`, `metrica`, `execucao`
- [ ] Implementar a camada de acesso ao banco em `src/barnes/db/`
- [ ] Implementar o preenchimento automático de `execucao` a cada processamento
- [ ] Implementar a captura do commit e a detecção de repositório com alterações não commitadas
- [ ] Implementar a restrição de integridade que impede métrica sem execução vinculada
- [ ] Implementar o catálogo de trials com animal, sessão, situação e cobertura de pose
- [ ] Implementar a verificação de hash e a sinalização de arquivo movido ou alterado
- [ ] Escrever teste de detecção de arquivo movido
- [ ] Escrever teste de rejeição de métrica órfã

#### Definição de Pronto (DoD Específica do Card)
- [ ] Tabela `execucao` implementada e preenchida automaticamente
- [ ] Restrição de integridade impedindo métrica sem execução
- [ ] Catálogo de trials consultável
- [ ] Verificação de hash implementada e testada com arquivo movido
- [ ] Detecção de repositório sujo implementada

---

### [US-28] Trial de referência versionado com teste de regressão

- **Épico / Módulo:** Qualidade e reprodutibilidade (`tests/fixtures/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S3

#### Narrativa de Usuário
- **Como** equipe de desenvolvimento,
- **Queremos** um trial de referência versionado, com resultado esperado e teste automatizado,
- **Para que** qualquer regressão introduzida por uma mudança apareça imediatamente, e não na semana 10, com cinco frentes integrando ao mesmo tempo.

#### Regras de Negócio & Escopo
- [RN01] `tests/fixtures/` contém um **vídeo curto** de referência e os **valores esperados** de todas as métricas.
- [RN02] O teste falha se **qualquer** métrica sair da tolerância declarada — as tolerâncias são as da seção de critérios de aceite do projeto.
- [RN03] O fixture é pequeno o bastante para ser versionado em Git e para o teste rodar em tempo aceitável em cada mudança.
- [RN04] Atualizar os valores esperados exige justificativa registrada no commit — atualizar o esperado para fazer o teste passar é exatamente o que este card existe para impedir.
- [RN05] O teste roda **antes** de qualquer merge na branch principal.
- [RN06] Card do Sprint 3, deliberadamente: é o primeiro sprint em que existem métricas para registrar como valor esperado, e ele existe para proteger os Sprints 4 e 5, quando cinco pessoas mexem em módulos interdependentes. Com código sendo produzido mais rápido por ferramentas de IA, este card deixa de ser higiene e passa a ser a principal defesa contra regressão silenciosa.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — pipeline íntegro**
  - **Dado que** o código está na versão de referência,
  - **Quando** o teste de regressão é executado sobre o fixture,
  - **Então** todas as métricas ficam dentro da tolerância e o teste passa.

- **Cenário 2: Detecção de regressão**
  - **Dado que** uma alteração no cálculo de eventos mudou a contagem de erros do fixture,
  - **Quando** o teste é executado,
  - **Então** ele falha identificando qual métrica saiu da tolerância e por quanto.

- **Cenário 3: Atualização legítima do esperado**
  - **Dado que** uma mudança de definição acordada em G3 alterou legitimamente o resultado esperado,
  - **Quando** os valores do fixture são atualizados,
  - **Então** o commit traz a justificativa e a referência à decisão que motivou a mudança.

#### Tarefas
- [ ] Selecionar e recortar um trecho curto de trial para servir de fixture
- [ ] Versionar o vídeo e seus metadados em `tests/fixtures/`
- [ ] Registrar os valores esperados de todas as métricas, com as tolerâncias da seção 10
- [ ] Implementar o teste de regressão comparando a saída do pipeline ao esperado
- [ ] Garantir tempo de execução aceitável para rodar a cada mudança
- [ ] Incorporar o teste ao fluxo obrigatório antes de merge na branch principal
- [ ] Documentar no README a política de atualização dos valores esperados

#### Definição de Pronto (DoD Específica do Card)
- [ ] Vídeo curto de referência versionado em `tests/fixtures/`
- [ ] Valores esperados de todas as métricas registrados com tolerância
- [ ] Teste automatizado implementado e executando em tempo aceitável
- [ ] Teste incorporado ao fluxo obrigatório antes de merge
- [ ] Política de atualização do esperado documentada no README

---

### [US-29] Relatório de concordância contra a anotação manual

- **Épico / Módulo:** Validação e entrega (`docs/`)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 8 Pontos · 1 semana (verificação — não acelera com IA)
- **Sprint:** S5

#### Narrativa de Usuário
- **Como** equipe de desenvolvimento,
- **Queremos** comparar todas as métricas automáticas com a anotação manual do laboratório,
- **Para que** os números entregues tenham prova documentada em vez de plausibilidade.

#### Regras de Negócio & Escopo
- [RN01] O relatório cobre **todos** os critérios de aceite do projeto: cobertura de pose ≥ 0,98; tempo de descoberta ≤ 0,5 s; tempo de entrada ≤ 0,3 s; sequência de buracos ≥ 0,95; erros ≤ 1; latência ≤ 1 s; distância r ≥ 0,95; kappa de estratégia ≥ 0,70.
- [RN02] Cada critério é reportado com o valor medido, o alvo e o veredito — atende ou não atende. Critério não medido é reportado como **não medido**, nunca omitido.
- [RN03] Este card **depende da anotação manual (D3)**, que é trabalho do laboratório e não do grupo. Deve estar agendado com data desde a semana 2; sem ele, três critérios ficam sem como medir.
- [RN04] A comparação dos hazard ratios automáticos contra os manuais, produzida em [US-25], entra no relatório como evidência principal — é a prova de que a extração automática substitui a anotação sem alterar a conclusão estatística.
- [RN05] Um critério que não atende é reportado como não atende. O relatório mede; não negocia o resultado.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Fluxo principal — relatório completo**
  - **Dado que** a anotação manual de D3 foi entregue,
  - **Quando** o relatório de validação é gerado,
  - **Então** cada um dos critérios da seção 10 aparece com valor medido, alvo e veredito.

- **Cenário 2: Evidência de equivalência estatística**
  - **Dado que** o `barnes_maze.py` rodou sobre a saída automática e sobre a anotação manual,
  - **Quando** os dois conjuntos de hazard ratios são comparados,
  - **Então** o relatório apresenta a comparação como evidência de que a substituição preserva a conclusão.

- **Cenário 3: Tratamento de exceção — critério não mensurável**
  - **Dado que** a anotação manual de estratégia não foi entregue a tempo,
  - **Quando** o relatório é gerado,
  - **Então** o critério de kappa aparece marcado como **não medido**, com a causa registrada — e não é omitido nem substituído por uma estimativa.

#### Tarefas
- [ ] Cobrar e receber a anotação manual completa de **D3**
- [ ] Implementar o relatório de concordância cobrindo os dez critérios da seção 10
- [ ] Implementar o relato de critério **não medido**, com a causa registrada
- [ ] Executar a validação e registrar valor medido, alvo e veredito por critério
- [ ] Incorporar ao relatório a comparação de hazard ratios produzida em [US-25]

#### Definição de Pronto (DoD Específica do Card)
- [ ] Relatório de concordância cobrindo todos os critérios da seção 10
- [ ] Comparação de hazard ratios automáticos contra manuais incorporada
- [ ] Critérios não medidos declarados com a causa

---

### [US-30] Empacotamento, manual e instalação assistida

- **Épico / Módulo:** Validação e entrega (`docs/`, empacotamento)
- **Prioridade Sugerida:** Alta
- **Complexidade Estimada:** 5 Pontos · 2,5–4 dias
- **Sprint:** S5

#### Narrativa de Usuário
- **Como** equipe de desenvolvimento,
- **Queremos** entregar o software empacotado, com manual, instalado e testado por alguém de fora,
- **Para que** o laboratório fique autônomo depois que a equipe sair.

#### Regras de Negócio & Escopo
- [RN01] A instalação é testada por **alguém de fora do grupo**, seguindo apenas o manual, sem ajuda.
- [RN02] Critério de usabilidade: o operador processa um trial sozinho, pelo manual, em **≤ 10 minutos**.
- [RN03] O software roda **offline** na máquina do laboratório, sem custo recorrente e sem dependência de nuvem para inferência.
- [RN04] Verificação final de licenças: nenhuma dependência GPL/AGPL na distribuição — inclusive as introduzidas por sugestão de ferramenta de IA durante o desenvolvimento.
- [RN05] O documento de entrega registra limitações conhecidas e trabalho futuro, incluindo o que foi cortado do escopo e por quê.

#### Critérios de Aceite (Cenários Executáveis / BDD)
- **Cenário 1: Instalação por terceiro**
  - **Dado que** uma pessoa de fora do grupo recebe o pacote e o manual,
  - **Quando** ela executa a instalação seguindo apenas o documento,
  - **Então** ela conclui a instalação sem contato com a equipe e processa o trial de exemplo com sucesso.

- **Cenário 2: Critério de usabilidade**
  - **Dado que** o operador do laboratório recebeu o manual,
  - **Quando** ele processa um trial do início ao fim sozinho,
  - **Então** o tempo total é **≤ 10 minutos**.

- **Cenário 3: Verificação de licenças**
  - **Dado que** o pacote final foi montado,
  - **Quando** as licenças das dependências são auditadas,
  - **Então** nenhuma dependência GPL ou AGPL está presente na distribuição.

- **Cenário 4: Operação offline**
  - **Dado que** a máquina do laboratório está sem rede,
  - **Quando** o operador processa um trial completo,
  - **Então** o pipeline roda de ponta a ponta sem falha de dependência externa.

#### Tarefas
- [ ] Escrever `docs/manual-usuario.md` com instalação, operação e dicionário de colunas
- [ ] Empacotar a distribuição para a plataforma do laboratório (resposta de D2)
- [ ] Testar a instalação com uma pessoa externa ao grupo, sem nenhuma ajuda
- [ ] Cronometrar o processamento de um trial pelo operador e verificar ≤ 10 min
- [ ] Auditar as licenças de todas as dependências da distribuição
- [ ] Instalar e validar o funcionamento offline na máquina do laboratório
- [ ] Registrar as limitações conhecidas e o trabalho futuro no documento de entrega

#### Definição de Pronto (DoD Específica do Card)
- [ ] `docs/manual-usuario.md` completo, com instalação, operação e dicionário de colunas
- [ ] Instalação validada por pessoa externa ao grupo, apenas com o manual
- [ ] Tempo de operação cronometrado e ≤ 10 min
- [ ] Auditoria de licenças concluída sem GPL/AGPL
- [ ] Pacote entregue e funcionando offline na máquina do laboratório

---

# Resumo do backlog

## Distribuição por sprint e esforço

| Sprint | Semanas | Cards | Story Points | Marco |
|---|---|---|---|---|
| **S1** | 1–2 | US-01, US-02, US-03, US-04, US-05, US-06 | 31 · **19,75 p-d** | **M1** — escopo congelado, definições assinadas |
| **S2** | 3–4 | US-07, US-08, US-09, US-10, US-11, US-27 | 31 · **19,75 p-d** | **M2** — trajetória com orientação e primeiro evento de buraco |
| **S3** | 5–6 | US-12, US-13, US-14, US-15, US-16, US-28 | 23 · **14,25 p-d** | **M3** — eventos calibrados e travados por teste de regressão |
| **S4** | 7–8 | US-17, US-18, US-19, US-20, US-21, US-22 | 32 · **20,00 p-d** | **M4** — métricas, estratégia e Incremento 1 entregues |
| **S5** | 9–10 | US-23, US-24, US-25, US-26, US-29, US-30 | 36 · **22,50 p-d** | **M5** — validação · **M6** — entrega |
| | | **6 cards por sprint · 30** | **153 pontos · 96,25 pessoa-dias** | |

> **p-d = pessoa-dias.** Conversão pela régua, usando o ponto médio de cada faixa: 3 → 1,75 dias · 5 → 3,25 dias · 8 → 5 dias · 13 → 10 dias.

## Os quatro movimentos em relação ao plano original

A contagem só fecha em 6/6/6/6/6 com uma cascata: o S1 precisa ganhar um card, e como **nenhum card do S5 pode ir para o S1** — todos dependem de trabalho do S2 ao S4 — a vaga desce degrau por degrau. Em cada degrau havia essencialmente um candidato legal.

| Card | De | Para | Por que o movimento é legítimo |
|---|---|---|---|
| **US-05** — rotação da plataforma | S2 | S1 | O portão **G2** (geometria e referencial) já fecha na semana 1. É geometria pura: a conversão índice↔sala não depende de pose, só da montagem e do valor de rotação. Mesmo módulo e mesmo responsável que US-04. Entregá-lo no S1 destrava US-24 e US-26 um sprint antes. |
| **US-10** — evento de descoberta | S3 | S2 | Único candidato possível: os demais cards do Épico D formam uma cadeia estrita a jusante dele. Fica no mesmo sprint que a série de pose de que depende — acoplamento real, aceito porque antecipa o risco fatal do projeto. |
| **US-18** — distância e velocidade | S4 | S3 | O pipeline do laboratório modela tempo e distância simetricamente. Separar a latência (S3) da distância (S4) partia um par sempre usado junto e adiava metade das colunas de `trials.csv`. |
| **US-24** — DTW / Fréchet | S5 | S4 | É exatamente a **opção 1 da seção 8** do `definicao-projeto.md`: proteger uma das análises avançadas trazendo-a para o S4. Suas duas entradas (US-05 e as trajetórias) já existem desde o S1 e o S2. |

## Como as estimativas foram calculadas

As pontuações usam a **régua de tempo absoluto** adotada pela equipe:

| Pontos | Tempo de uma pessoa |
|---|---|
| 0 | < 2 horas |
| 1 | 2 a 4 horas |
| 2 | 8 horas (1 dia) |
| 3 | 1,5 a 2 dias |
| 5 | 2,5 a 4 dias |
| 8 | 1 semana (5 dias) |
| 13 | 2 semanas — **deve ser quebrado** |

O procedimento foi: somar o esforço das tarefas de cada card em dias de uma pessoa, e **aplicar um multiplicador de aprendizado** correspondente ao nível da equipe — cinco integrantes em nível de estagiário. O multiplicador não é uniforme; depende de quanto conteúdo novo o card exige:

O multiplicador incide sobre *aprendizado*, não sobre digitação. E como a equipe usa ferramentas de IA, ele é reduzido — mas de forma desigual, porque a IA comprime aprendizado e código, não trabalho humano nem calendário.

| Natureza do trabalho | Estagiário | Com IA | Cards |
|---|---|---|---|
| Python e pandas sobre dados já estruturados | ×1,5 | **×1,0** | US-14, US-15, US-17, US-22, US-23 |
| OpenCV, vídeo, geometria, empacotamento | ×2 | **×1,4** | US-01 a US-05, US-10, US-13, US-16, US-18, US-19, US-24, US-25, US-27, US-30 |
| SLEAP, redes de pose, algoritmo com calibração | ×2,5–3 | **×1,8** | US-06, US-07, US-08, US-09, US-11, US-20, US-26 |
| **Verificação** — o multiplicador **não** é reduzido | ×2–2,5 | **×2–2,5** | US-12, US-21, US-28, US-29 |

### O que a IA não acelera

Cerca de 20 dos 96,25 pessoa-dias são imunes, e por isso a redução foi de 27%, não de 50%. **As três quebras de card seguem exatamente essa fronteira**, isolando a metade imune num card próprio, que pode escorregar sem travar a outra:

| Trabalho | Card | Por quê |
|---|---|---|
| Anotar os quadros no SLEAP | US-06 | Trabalho humano de marcação, ponto a ponto |
| Treinar o modelo | US-07 | Tempo de GPU é relógio de parede |
| Calibrar limiares contra a anotação manual | **US-12**, US-13, US-21 | O gargalo é a anotação do laboratório e a iteração com o pesquisador |
| Obter respostas do laboratório | G1–G3, blocos A–D | Depende da agenda de outras pessoas |
| Instalação por terceiro, cronometragem, aceite do PI | **US-30** | Calendário e pessoas |

### Por que a verificação não foi reduzida

A definição do projeto identifica como risco fatal o software produzir *"números coerentes, plausíveis, bem formatados — e sem relação com o que o laboratório chama de latência"*. Ferramentas de IA aceleram exatamente a produção de saída coerente, plausível e bem formatada, e uma equipe em nível de estagiário tem menos capacidade de perceber quando o resultado está errado — sobretudo em estatística, onde um modelo de Cox com censura codificada ao contrário roda e devolve números.

Consequência prática: **[US-12], [US-21], [US-28] e [US-29] mantêm a estimativa integral**, e [US-28] (trial de referência e teste de regressão) deixa de ser higiene e passa a ser a principal defesa do projeto. Espera-se também mais tentativas de dependência GPL entrando por sugestão de IA — `pingouin` é o caso que os próprios documentos citam, e a auditoria de licenças de [US-30] passa a ter probabilidade maior de encontrar algo.

**Limitação declarada:** tanto o multiplicador de estagiário quanto a redução por IA são hipóteses do grupo, não medições. A velocidade real do Sprint 1 é o primeiro dado empírico e deve recalibrar todo o restante do backlog no planejamento do Sprint 2 — com IA isso fica mais importante, não menos, porque a incerteza sobre a produtividade real é maior.

## Análise de capacidade

Com a régua absoluta, o backlog deixa de ser uma lista de tamanhos relativos e passa a ser uma conta verificável. **96,25 pessoa-dias** distribuídos por 5 integrantes em 10 semanas exigem **~19 dias de trabalho por pessoa**, ou **1,9 dia por semana, por pessoa**, ao longo do semestre.

| Dedicação de cada integrante | Capacidade total | Situação |
|---|---|---|
| 1 dia/semana (~8 h) | 50 p-d | **92% acima** — inviável |
| 1,5 dia/semana (~12 h) | 75 p-d | **28% acima** — exige corte |
| 2 dias/semana (~16 h) | 100 p-d | **Cabe**, com folga de 4% |
| 2,5 dias/semana (~20 h) | 125 p-d | Cabe com folga de 23% |

A carga entre sprints ficou plana: **de 14,25 (S3) a 22,5 (S5) pessoa-dias**, amplitude de 8,25. O S3 é deliberadamente mais leve — é o sprint seguinte ao aperto de pose e serve de colchão para o que escorregar do S2. Vale manter assim: se trabalho for puxado para dentro dele, o colchão desaparece.

**Nenhum card permanece em 13 pontos.** As três quebras ([US-07], [US-10], [US-30]) resolveram os casos que a régua marcava como obrigatórios, e o maior card do backlog agora é de 8 pontos.

Alavancas restantes, caso a dedicação acordada fique abaixo de 2 dias por semana:

1. **Cortar a metade de palpites de [US-26]** — a análise menos definida do backlog, dependente da resposta de B7. Decisão no planejamento do Sprint 4.
2. **Preparação antecipada** — se um integrante fizer o tutorial de SLEAP antes da semana 1, [US-06], [US-07] e [US-09] deixam de carregar o multiplicador cheio.
3. **Declarar [US-24] (DTW) como trabalho futuro** — é a contribuição de originalidade protegida, então este é o último corte, não o primeiro.
4. **Rever a dedicação semanal acordada** e registrá-la na proposta, para que o professor avalie o escopo contra a carga real da disciplina.

## Por que certos cards são maiores do que o enunciado sugere

A tabela abaixo foi levantada na revisão em que as estimativas ainda eram **relativas**, antes da régua de tempo absoluto e do multiplicador de estagiário. **Os números das colunas "Antes" e "Depois" não são os vigentes** — os atuais estão em cada card e na tabela de distribuição acima. Ela é mantida porque o raciocínio de cada linha continua válido e explica por que esses cards custam mais do que a leitura da história indica.

Os cards são identificados por nome, não por número, porque a numeração mudou desde então.

| Card | O que a lista de tarefas revelou |
|---|---|
| **Recorte do intervalo útil** | A detecção automática do evento S é uma heurística sobre vídeo, não um recorte de índices. Estava precificada como se fosse configuração. |
| **Carga do vídeo** | Medir fps real, detectar fps variável e trocar a base temporal são três problemas distintos, não um. |
| **Anotação de quadros** | A tarefa "anotar os quadros" é a maior linha de esforço humano do Sprint 1 e estava diluída entre tarefas de infraestrutura. |
| **Distância e velocidade** | A segmentação da trajetória pelas fases S→D, D→E e S→E é trabalho próprio, separado de integrar a distância. |
| **Eficiência de rota** | Detectar o ponto de soltura por trial é a mesma heurística incerta do recorte — a razão em si é trivial, a detecção não. |
| **Kappa** | O card não é "calcular kappa": é o **loop de ajuste** da regra de classificação quando o kappa reprova. Estava precificada só a primeira linha da lista. |
| **Exportação compatível** | Compatibilidade nunca é de graça. Rodar o `barnes_maze.py` sem alteração é um teste de integração iterativo, não uma verificação. |
| **Validação e entrega** | Relatório de concordância, manual, empacotamento, instalação por terceiro, auditoria de licenças e instalação offline — cinco entregas distintas num card. Foi o que motivou a quebra. |
| **Probe e palpites** | **Único card que encolheu.** A dificuldade é conceitual, não volumétrica: com o referencial da sala pronto, sobram duas análises e uma saída em CSV. |

**Sobre probe e palpites:** a queda enfraquece o argumento de cortá-lo por volume — cortar 5 pontos alivia pouco. O motivo para mantê-lo como candidato a corte não é o tamanho: é que a análise de palpites é a menos definida do backlog e depende da resposta de B7, que ainda não veio.

## As três quebras de card

Pela régua, 13 pontos significa duas semanas de uma pessoa — um card que ocupa metade de um sprint sozinho e não pode ser concluído nem medido dentro dele. Três cards foram divididos, e o critério é o mesmo nos três: **separar a metade que a equipe controla da metade que depende de terceiros.** A segunda pode escorregar sem travar a primeira.

| História de origem | Metade que a equipe controla | Metade dependente de terceiros |
|---|---|---|
| **7** — Modelo de pose treinado | **[US-07]** Ambiente e treino (5) · S2 | **[US-08]** Avaliação por região e inferência local (3) · S2 |
| **10** — Evento de descoberta | **[US-11]** Detecção e persistência dos eventos (5) · S2 | **[US-12]** Calibração contra a anotação manual (3) · S3 — depende de **D3** |
| **30** — Validação e entrega | **[US-30]** Empacotamento, manual e instalação (5) · S5 | **[US-29]** Relatório de concordância (8) · S5 — depende de **D3** |

Os cards ficaram contíguos por sprint, o que mantém o quadro legível: S1 = US-01 a 06, S2 = US-07 a 11 + 27, S3 = US-12 a 16 + 28, S4 = US-17 a 22, S5 = US-23 a 26 + 29 e 30.

## Rastreabilidade com as histórias da proposta

| Cards | Histórias de origem |
|---|---|
| US-01 a US-06 | 1 a 6 — sem alteração |
| US-07, US-08 | história 7, dividida |
| US-09, US-10 | histórias 8 e 9 |
| US-11, US-12 | história 10, dividida |
| US-13 a US-22 | histórias 11 a 20 |
| US-23 a US-26 | histórias 23 a 26 |
| US-27, US-28 | histórias 28 e 29 |
| US-29, US-30 | história 30, dividida |
| — | histórias **21, 22 e 27**: fora de escopo |

## Dependências críticas entre cards

| Card | Depende de | Natureza |
|---|---|---|
| Todos do Épico D | **G3** (definições operacionais assinadas) | Externa, bloqueante para aceite |
| US-08 | US-07 (**mesmo sprint**) | Técnica — ordenação obrigatória dentro do S2 |
| US-11 | US-04 (S1), US-09 e US-10 (**mesmo sprint**) | Técnica — ordenação obrigatória dentro do S2 |
| US-12 | US-11 (S2) + **D3** (anotação manual) | Externa, bloqueante |
| US-13 | US-11 (S2), US-09, US-10 | Técnica |
| US-15 | US-11, US-13 | Técnica — contrato de dados |
| US-17, US-20 | US-15 (S3) | Técnica — fonte única |
| US-18 | US-09 (S2), US-11 (S2), US-13 (S3) | Técnica — velocidade por fase exige o evento E |
| US-21 | US-20 (**mesmo sprint**) + **D3** | Externa, bloqueante |
| US-24, US-26 | US-05 (S1 — referencial da sala) | Técnica — sem isso, resultado sem significado |
| US-25 | US-16 (S3), US-18 (S4) | Técnica — é a única ponte para a análise do laboratório |
| US-29 | **D3** + US-25 (**mesmo sprint**) + todos os demais | Externa e técnica |

Três pares dividem sprint com sua própria dependência: **US-07 → US-08** (S2), **US-09 → US-11** (S2) e **US-20 → US-21** (S4). Nesses casos a ordem dentro do sprint é obrigatória e deve aparecer no quadro como bloqueio explícito, não como preferência de sequenciamento.

## Definição de Pronto global do projeto

Aplica-se a todo sprint, além da DoD específica de cada card. Cerimônias não são itens de backlog — não viram card — mas condicionam o fechamento do sprint.

- [ ] **Review quinzenal com o professor/cliente** ao final do sprint, com o incremento demonstrado sobre dados reais
- [ ] Retrospectiva realizada e decisões registradas
- [ ] **Velocidade real do sprint medida** e comparada com a estimada, com a diferença usada para recalibrar o backlog restante
- [ ] Teste de regressão de [US-28] passando antes de qualquer merge na branch principal
- [ ] Nenhuma dependência GPL/AGPL introduzida no sprint
- [ ] Riscos do registro revisados; riscos novos adicionados

> A cadência de reuniões quinzenais coincide exatamente com a fronteira dos sprints de duas semanas — uma review por sprint, sem cerimônia extra.

## Bloqueios externos que atravessam o backlog

Três respostas do laboratório destravam a maior parte deste backlog e nenhuma está sob controle da equipe:

- **G3 / Bloco C — limiares operacionais.** Sem eles, os cards do Épico D são desenvolvíveis mas **não são aceitáveis**. É o marco M1.
- **B1 — tamanho do conjunto.** Define se [US-23] produz inferência ou descrição com ressalva, e se a análise do laboratório sobre os dados automáticos terá poder estatístico. Precisa ser respondido na semana 1, não descoberto na semana 9.
- **B4 — rotação da plataforma.** Define se [US-05] é conversão real ou identidade, e com isso a validade de [US-24] e [US-26].
- **D3 — anotação manual.** É hora de trabalho do laboratório, não do grupo. Sem ela, três critérios de aceite não têm como ser medidos e [US-12], [US-21] e [US-29] não fecham. **Agendar com data marcada.**

---

# Fora de escopo

Removidos do backlog por já existirem no laboratório. O `barnes_maze.py` roda hoje, e [US-25] entrega os dados no formato que ele consome sem alteração.

Identificados pelo número da **história na proposta original**, não pelo número de card — eles não têm card, e os números 21, 22 e 27 foram reaproveitados na renumeração.

| História removida | Já existe como | Economia |
|---|---|---|
| **21** — Regressão de Cox | `model_latency_s_d()`, `model_distance_s_d()`, `model_latency_d_e()`, `model_distance_d_e()`, `model_latency_s_e()`, `model_distance_s_e()` | 8 pts · 5 p-d |
| **22** — Incidência cumulativa e forest plot | `plot_cumulative_incidence_discovery_pathway()`, `plot_cumulative_incidence_decision_latency()`, variantes para probes, e as figuras de hazard ratio via `cph.plot()` | 5 pts · 3,25 p-d |
| **27** — Relatório PDF por animal | O documento executável do laboratório — código, figuras e interpretação no mesmo arquivo, regenerável | 5 pts · 3,25 p-d |

**Total: 18 pontos · 11,5 pessoa-dias.**

A contribuição do projeto é substituir anotação manual por extração automática mantendo compatibilidade — reimplementar a estatística do cliente não reforça essa tese. Em consequência, **[US-25] passa a ser o único ponto de validação estatística**: sua tarefa de rodar o `barnes_maze.py` sobre a saída automática deixa de ser verificação de integração e vira a prova central do trabalho, incorporada ao relatório de [US-29].

Também fora de escopo, herdado da definição do projeto: múltiplos animais e interação social, análise em tempo real, etogramas complexos, classificação de estratégia por aprendizado de máquina.

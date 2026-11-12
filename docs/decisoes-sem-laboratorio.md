# Decisões da equipe sem contato com o laboratório (LNBio)

**Status: convenção de trabalho da equipe — não é o aceite G3 de
`docs/definicoes-metricas.md`.**

> O contato direto com o LNBio, previsto no plano original, não ocorreu.
> Para não travar o desenvolvimento, a equipe decidiu internamente os itens
> abaixo. Nenhuma resposta aqui vem do laboratório. Se o LNBio responder
> antes do fim do projeto, cada item deste documento é revisado contra a
> resposta real — nunca o contrário. Isto não fecha o portão G3 de
> `docs/definicoes-metricas.md`: não há assinatura do laboratório (C6). Os
> valores aprovados aqui entram em `configs/default.yaml` **marcados como
> decisão da equipe** (seção 16), e o relatório declara a limitação.

**Fontes, em ordem de força:**

1. o `barnes_maze.py` do laboratório (na raiz de `Gerenciamento_projetos`, fora
   deste repositório), que é o código que vai consumir a saída — o que ele
   mostra é **evidência**, não resposta;
2. a literatura do método (seção Referências) — **as citações não foram
   conferidas página a página**; conferir antes de citar no relatório;
3. convenção da equipe, quando não há nem uma coisa nem outra.

**Situação em 12/11/2026: todas as seções aprovadas pela equipe.** As seções 1,
2, 3 e 5 já eram decisões anteriores; 11 a 13 vieram de uma versão paralela
deste documento e receberam complementos; 4, 6 a 10 e 14 a 16 foram propostas e
aprovadas em 12/11/2026. Os ajustes no repositório decorrentes estão listados
na seção 17.

Questões do comitê de ética (CEUA, D4) estão fora do escopo deste documento.

## 1. Buraco de referência (US-05, §6.2 de `definicoes-metricas.md`)

**Decisão: identificação visual e manual, feita por quem monta a configuração.**

A câmera só vê a plataforma de cima (sem marco de parede) e não há como
perguntar ao laboratório qual buraco já usam como referência física. Critério
adotado:

- Ao rodar `barnes maze create` para um novo vídeo do mesmo experimento, o
  operador compara visualmente o quadro de referência com a montagem
  anterior já salva (`barnes maze show <id anterior>`) e escolhe **o mesmo
  buraco físico**, apoiado em qualquer marca estável entre sessões — desgaste
  do material, diferença de cor/textura na borda do buraco, posição relativa
  a um elemento fixo visível na borda do quadro (canto de sala, objeto fixo,
  fio), ou qualquer outro detalhe que se repita vídeo a vídeo.
- Esse buraco é sempre gravado como hole 0 (buraco de referência) na nova
  montagem, mesmo que a câmera tenha se deslocado — é o caso que
  `maze_configs`/`holes` já cobre (nova montagem, mesmo buraco físico).
- Não há verificação automática da escolha. É uma decisão humana registrada
  no momento da montagem; erro de identificação só é detectável por
  inspeção cruzada de outra pessoa da equipe, nunca pelo software.

Isso substitui, por ora, a fita/marca física que um laboratório real usaria
— a equipe não tem acesso físico ao equipamento do LNBio para colocar uma
marca real.

> **Limite deste critério:** marcas de desgaste ou cor estão **na plataforma**.
> Só identificam um ponto fixo da sala se a plataforma não rotaciona (seção 13).
> Se rotacionasse, a marca giraria junto e o "buraco 0" seguiria a plataforma,
> não a sala. Nesse caso, valem só os elementos fixos na borda do quadro.

## 2. Soltura do animal (B3, US-03/US-19)

**Confirmado como padrão do método, não tratado como pendência real.**

Soltura por cilindro opaco no centro da plataforma — animal colocado sob o
cilindro, habituação, cilindro removido para iniciar o trial — é como o
Barnes maze funciona por desenho (Barnes, 1979; protocolo descrito em
Sunyer et al., 2007, *Nature Protocols*). Não varia entre laboratórios do
jeito que, por exemplo, o critério de "entrar" varia. Assume-se que os
vídeos do LNBio seguem esse desenho: o animal aparece solto no centro
quando o cilindro é retirado, e esse instante é o evento **S** (US-03 RN03).

> Os vídeos reais vistos até aqui já começam com o animal solto
> (`docs/ROTEIRO-DEMONSTRACAO.md`, pendências da US-03). Nesse caso o início do
> vídeo é tratado como S, e o intervalo útil começa no quadro 0.

## 3. Velocidades por fase (US-18, US-25)

**Decisão: `trials.csv` não leva colunas de velocidade.**

`primary_speed`, `decision_speed` e `total_speed` são derivadas por
`barnes_maze.py` a partir de distância e latência — não precisam ser colunas
de entrada do projeto. Já é consistente com RN01 de US-25 (seção 4 abaixo),
que não lista nenhuma coluna de velocidade. O projeto entrega distância e
latência; a conversão para velocidade continua responsabilidade do script do
cliente.

Evidência: `barnes_maze.py:11-32` e `:49-51` (trials) e `:280-290` (probes).
No probe, o script usa `probe_time = 90` fixo (seção 11).

## 4. Esquema de `trials.csv` / `probes.csv` (US-25, US-26)

**Decisão: o esquema é o que o `barnes_maze.py` lê.** A versão anterior desta
seção foi inferida dos cards e divergia do script em três pontos: definia
`primary_*` como "até a primeira entrada", fazia `total_*` igual a
`primary_*` e propunha um `probes.csv` com colunas que o script não lê. Um
arquivo naquele formato quebraria o critério de aceite da US-25 (rodar o
script sem alteração).

### Unidades

- **Latências em segundos.**
- **Distâncias em metros.** Os gráficos do script rotulam o eixo de
  distância como `"Distance (m)"`, com limite de 8 (`barnes_maze.py:144`,
  `:201`, `:325`, `:363`). O software calcula em **cm** internamente
  (US-02, US-13, US-16, US-18); **a exportação da US-25 converte para metros**
  todas as colunas de distância, inclusive as complementares (`path_distance`
  da US-18). Exportar em cm não quebra o script nem os hazard ratios do grupo
  (o modelo de Cox só usa a ordem dos valores), mas deixa os gráficos e as
  velocidades 100 vezes fora da escala do laboratório.

### `trials.csv`

Colunas que o script usa (`barnes_maze.py:36-123` e `:139-271`):

| Coluna | Tipo | Unidade | Significado | Origem no software |
|---|---|---|---|---|
| `animal` | texto | — | id do sujeito; o Cox agrupa por ele (`cluster_col`) | `subjects` |
| `group` | texto | — | grupo; `"WT"` vira `mutation = 0`, qualquer outro valor vira 1 | experimento |
| `day` | inteiro | — | dia da aquisição (o script plota dias 1 a 4) | `trials.day_number` |
| `trial` | inteiro | — | trial do dia (o script plota 1 a 4) | `trials.trial_number_in_day` |
| `primary_latency` | float | s | S→D: soltura até a **descoberta** do alvo | US-16 |
| `primary_distance` | float | m | distância percorrida de S a D | US-16 |
| `primary_event` | 0/1 | — | 1 = descobriu o alvo dentro do tempo limite; 0 = censurado | US-16 |
| `delta_latency` | float | s | D→E: hesitação entre descobrir e entrar | US-13 |
| `delta_distance` | float | m | distância percorrida de D a E | US-13 |
| `total_latency` | float | s | S→E: soltura até a **entrada** no alvo | US-16 |
| `total_distance` | float | m | distância percorrida de S a E | US-16 |
| `total_event` | 0/1 | — | 1 = entrou no alvo dentro do tempo limite; 0 = censurado | US-16 |

`total_*` **não** é igual a `primary_*`: a diferença entre os dois é exatamente
a fase de decisão que o script modela (`speed_decision` usa `delta_*`). O
script soma 1e-3 a `delta_*` quando algum valor é ≤ 0
(`barnes_maze.py:38-48`), então hesitação zero é aceitável.

Colunas adicionais do projeto (estratégia, entropia, eficiência de rota,
cobertura de pose, id de execução, colunas da US-18 — RN04/RN05 de US-25) vão
**ao final do arquivo** ou em arquivo complementar, nunca inseridas entre as
colunas acima.

### `probes.csv`

Colunas que o script usa (`barnes_maze.py:276-365`):

| Coluna | Tipo | Unidade | Significado |
|---|---|---|---|
| `animal` | texto | — | id do sujeito (`cluster_col`) |
| `group` | texto | — | `"WT"` ou outro |
| `probe` | inteiro | — | **0** = primeiro probe, **1** = segundo (o comentário do script diz "day 5 and 12") |
| `primary_latency` | float | s | soltura até a descoberta do buraco-alvo antigo; 90 se não descobriu |
| `primary_distance` | float | m | distância até essa descoberta; até o fim do probe se não descobriu |
| `total_latency` | float | s | duração do probe: 90 |
| `total_distance` | float | m | distância percorrida no probe inteiro (é a `path_distance` da US-18 sobre o probe) |

O script **não** lê `primary_event` do arquivo: ele o calcula como
`primary_latency < total_latency` (`:291-293`). Por isso o probe censurado
precisa sair com `primary_latency` **igual** a `total_latency` (90), e não
vazio. As colunas `time_target_region_s`, `guess_correlation` etc. que esta
seção propunha antes são da US-26 e vão em arquivo complementar, não no
`probes.csv`.

Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas) (inclui a conversão das distâncias para metros)

## 5. Anotação manual (D3 — US-12, US-13, US-15, US-18, US-21)

**Decisão: fica como pendência explícita até o fim do projeto.**

Sem anotador do laboratório disponível, a equipe não produz anotação manual
própria agora. Estratégia:

1. Procurar, até o fim do projeto, um dataset público de Barnes maze com
   anotação manual de posição/eventos já pronta (candidatos a verificar:
   material complementar de Illouz et al. 2016, *Scientific Reports*; Attar
   et al. 2013, *PLoS ONE*; repositórios de rastreamento comportamental tipo
   DeepLabCut/SLEAP com exemplos de Barnes maze — nenhum confirmado ainda,
   isto é uma lista de busca, não uma fonte garantida).
2. Se nada for encontrado no formato necessário (trajetória + eventos de
   descoberta/entrada + sequência de visitas + estratégia rotulada), a
   calibração de US-12/US-13/US-21 e a validação de distância de US-18
   continuam sem poder fechar — vai para o relatório final como limitação
   externa, não falha da equipe, no mesmo registro já existente em
   `docs/definicoes-metricas.md` §4.1 (entrega D3 não confirmada em
   05/11/2026) e em `docs/status-us12-us13.md`.
3. Nenhum valor provisório de calibração é criado para simular essa entrega.
   O ferramental (`barnes events calibrate`, kappa de estratégia) continua
   coberto por teste sintético, nunca citado como validação real.

> **Opção em aberto para a US-18 (SCRUM-225).** A distância manual é bem mais
> barata que a anotação de eventos: basta marcar a posição do centro do corpo a
> cada k quadros em 10–15 trials. Se a equipe quiser fechar o r ≥ 0,95, pode
> medir ela mesma, desde que (a) sobre inferência de pose real, (b) com o método
> registrado no CSV (`barnes metrics distance-validate`) e (c) declarado no
> relatório como referência da equipe, não do laboratório. Sem isso, vale o
> item 2 acima.
>
> Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas) · opção: manter como limitação (medir continua possível se sobrar tempo)

## 6. Tempo limite do trial (B5 — US-16)

**Decisão: 180 s; trial sem entrada no alvo até lá é censurado.**

- Sem este valor, `trial.tempo_limite_s` fica `null` e a US-16 recusa calcular
  `primary_event`/`total_event` — o `trials.csv` não sai.
- Evidência no script: o gráfico de latência de decisão dos trials vai até
  180 s (`barnes_maze.py:211`, `:266`) e o do probe até 90 s, que coincide com
  a duração do probe (`:277`, `:373`). É **indício**, não prova: o eixo de 180 s
  é o da fase D→E, não o da latência total.
- Na literatura do método, tentativas de aquisição de alguns minutos, com o
  animal conduzido à caixa de fuga quando não a encontra, são o desenho usual
  (Sunyer et al., 2007 — conferir a duração exata no protocolo).
- Censura (já implementada, US-16): sem evento até o limite → `*_event = 0`,
  latência = 180 e distância = percorrida até 180 s. O trial nunca é
  descartado.

Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas) · valor: 180 s

## 7. Entrar e dwell (C2 — US-13, US-14)

**Decisão:**

| Chave | Valor | Por quê |
|---|---|---|
| `entrar.focinho_dentro` | `true` | já é o padrão; "entrar" = o focinho dentro do buraco (nose poke) |
| `entrar.raio_fator` | `1.0` | a área de entrada é o próprio buraco físico calibrado, sem margem |
| `entrar.duracao_minima_s` | `0.2` | 5 quadros a 25 fps: exclui um quadro isolado de ruído de pose sem exigir permanência longa; é o mesmo tamanho da lacuna curta da US-10 |
| `dwell.duracao_minima_s` | `null` | não é lido pelo cálculo (US-14 mede o dwell de toda entrada) |

- A duração mínima é um valor **técnico** (filtro de ruído), não uma definição
  comportamental; um valor maior transforma "olhar de passagem" em "não
  entrou" e muda `delta_latency`.
- Sem anotação (seção 5), nenhum desses valores é calibrado; a US-13 continua
  "implementada, não aceita".

Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas)

## 8. Erro (C3 — US-17)

**Decisão: `erro.criterio = qualquer_buraco_incorreto` (e
`erro.duracao_minima_s = null`).**

- É a contagem usual de erros no Barnes maze: cada checagem de um buraco que
  não é o alvo (Sunyer et al., 2007; Harrison et al., 2006 — conferir).
- A duração já é filtrada uma vez pela entrada (seção 7): só vira checagem o
  que passou de 0,2 s com o focinho no buraco. Exigir de novo uma duração no
  erro filtraria duas vezes.
- As três perguntas abertas na nota da US-17 (`definicoes-metricas.md`):
  - **revisita a um buraco errado conta como novo erro:** sim (já é o
    comportamento implementado);
  - **limite inclusivo (≥):** não se aplica com este critério;
  - **erros depois de achar o alvo entram no total:** sim em `total_errors`
    (trial inteiro); `primary_errors` conta só até a descoberta do alvo.
- Sem este valor, a US-17 — agora no Sprint 3 — recusa contar.

Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas)

## 9. Ponto do corpo para distâncias (US-13, US-16, US-18)

**Decisão: centro do corpo (`centro_corpo`), para todas as distâncias.**

- É o que o software já usa nas três histórias; o focinho percorre mais
  caminho que o corpo (movimentos de cabeça) e inflaria toda distância.
- "Distância percorrida" pelo ponto central do corpo é a convenção comum de
  software de rastreamento comercial (ex.: center-point do EthoVision) — não é
  citação verificada.
- Hoje o ponto é uma constante de código (`metrics.latency.DEFAULT_DISTANCE_POINT`).
  Se a equipe preferir, vira chave de configuração única para as três
  histórias.

Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas)

## 10. Estratégias de busca (C4 — US-20, US-21)

**Decisão: as três categorias de Harrison et al. (2006), em regra explícita
sobre a sequência de visitação da US-15 até a primeira checagem do alvo.**
Definições a conferir no artigo antes de usar como citação:

- **Espacial:** vai direto ao alvo ou a um buraco vizinho dele, com poucos
  erros antes (proposta: até 3) e sem cruzar o centro da plataforma.
- **Serial:** visita ao menos 2 buracos adjacentes em sequência, no mesmo
  sentido (horário ou anti-horário), antes do alvo.
- **Aleatória:** qualquer busca que não se encaixe nas duas acima, típica
  com cruzamentos pelo centro.

Mapeamento proposto para `configs/default.yaml` — a revisar quando a US-20 for
implementada, porque a semântica exata das chaves é dela:

| Chave | Proposta | Observação |
|---|---|---|
| `estrategia.adjacencia_angular_graus` | `360 / N` (um buraco de distância; 18° com 20 buracos) | depende de B2 (seção 12) |
| `estrategia.erros_ate_alvo_max` | `3` | limite da busca espacial |
| `estrategia.cruzamentos_centro_min` | `1` | um cruzamento do centro antes do alvo já descaracteriza a busca espacial |
| `estrategia.entropia_max_espacial` | `null` | não faz parte da regra de Harrison; só se a equipe quiser um critério adicional |

Sem anotação (seção 5), o kappa da US-21 não tem contra o que ser medido.

Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas)

## 11. Comportamento do probe (B7 — US-25, US-26)

**Resposta: no LNBio a plataforma é limpa.**

Conforme informado pela equipe, no probe trial do LNBio nenhum buraco é
fisicamente fechado ou removido — a plataforma é apenas limpa entre
animais (remoção de pistas olfativas que poderiam indicar o buraco-alvo
pelo cheiro, não pela posição). Consequência para US-26 (RN04):

- O buraco-alvo antigo não tem nenhuma marca física distinta dos demais
  durante o probe; a única forma de identificar "a região correta" é pela
  posição no referencial da sala (`target_hole_room`, US-05), nunca por
  sinal físico visível no vídeo.
- Não há caixa de escape sob nenhum buraco durante o probe (senão o animal
  escaparia e o teste de memória perderia o sentido) — mas isso não muda o
  que a visão computacional precisa fazer: o pipeline já detecta checagem
  por proximidade/orientação (US-11/US-13), independente de haver ou não
  escape físico sob o buraco.
- Isso fecha a pendência de RN04 de US-26: a "região do alvo antigo" é
  definida só pela posição na sala.

Esta resposta vem do conhecimento da equipe sobre o protocolo real do
LNBio, não de literatura nem de contato formal registrado — mantém o
mesmo status das demais decisões deste documento (convenção de trabalho,
não aceite G3).

> **Complemento (12/11/2026), a partir do `barnes_maze.py`:**
>
> - **Duração: 90 s.** O script usa `probe_time = 90` fixo
>   (`barnes_maze.py:277`) para todos os probes. Um probe gravado com outra
>   duração precisa ter o intervalo útil (US-03) recortado em 90 s, senão
>   `decision_speed` e `total_speed` do script saem errados.
> - **Dois probes por animal**: coluna `probe` = 0 e 1 (o comentário do
>   script diz dias 5 e 12). O trial é identificado por `trials.phase = 'probe'`.
> - **Colunas do `probes.csv`:** as de `primary_*`/`total_*` da seção 4. Sem
>   caixa de escape, `primary_*` é a **descoberta** (D) do buraco-alvo antigo e
>   `total_*` é o probe inteiro. As medidas da US-26 (`target_hole_room`, tempo
>   e checagens na região do alvo, correlação com palpites) não fazem parte do
>   `probes.csv` que o script lê: vão em arquivo complementar.

## 12. Medidas físicas da plataforma e dos buracos (B2 — US-02, US-04, US-20)

**Resposta: não precisa ser resolvido — já é entrada do operador.**

`barnes maze create` já recebe `--arena-diameter-cm` e `--hole-diameter-cm`
como parâmetros por montagem (US-04). A pergunta B2 nunca precisou de uma
resposta única e global do laboratório: quem monta uma montagem real mede
o aparato físico que tem em mãos (fita métrica, ou a própria calibração
px→cm de US-02) e informa o valor naquele comando. 92 cm / 5 cm continuam
sendo só os valores do roteiro de demonstração
(`docs/ROTEIRO-DEMONSTRACAO.md`), nunca uma constante do código. Não fica
pendência real aqui — só faltava registrar explicitamente que o desenho já
resolve isso, sem precisar de resposta do LNBio.

> **Complemento (12/11/2026): o que continua sendo suposição.**
>
> - **Onde os centímetros nascem.** Os dois diâmetros do `maze create` quase não
>   entram no cálculo: `arena_diameter_cm` só alimenta uma heurística da
>   detecção automática de buracos (`cli.py:755`). A escala px→cm de todas as
>   distâncias vem do `barnes scale calibrate`, que exige **comprimentos físicos
>   conhecidos** visíveis na imagem (`--length-1-cm`/`--length-2-cm`).
> - **Quem mede.** "Quem monta mede o aparato que tem em mãos" vale para um
>   operador do laboratório. Para os vídeos que **a equipe** processa, não vale:
>   a seção 1 registra que a equipe não tem acesso físico ao equipamento. Nesse
>   caso, o comprimento usado na calibração é uma dimensão **assumida** (por
>   exemplo, o diâmetro usual de 92 cm do labirinto para camundongos), e todas
>   as distâncias ficam condicionadas a ela.
> - **Impacto limitado.** Um erro de escala multiplica todas as distâncias pelo
>   mesmo fator. Isso não muda os hazard ratios do Cox, que só usa a ordem dos
>   valores, nem a correlação da US-18. Muda os valores absolutos em metros e as
>   velocidades. O relatório declara a dimensão assumida.
> - **Número de buracos.** É contado no próprio vídeo, não é suposição. Define
>   a adjacência das estratégias (seção 10).

## 13. Rotação da plataforma (B4 — US-05) — proveniência da resposta

**Resposta: tratado como escolha do operador por trial, não fato único do laboratório.**

A pendência registrada em `docs/definicoes-metricas.md` §6.1 ("Respondido
por: a preencher · Data: a preencher") pede uma pessoa e uma data reais do
LNBio — isso não existe e não pode ser fabricado neste documento.

A saída adotada não substitui essa proveniência por um nome fictício; em
vez disso, muda o que está em jogo: `trials.rotation_deg` já é, por
arquitetura, **sem DEFAULT** no banco (migração `0004`) — todo trial tem a
rotação gravada explicitamente no carregamento (`barnes video load
--rotation-deg`) ou corrigida depois via `barnes trial set-rotation`. Um
trial sem rotação registrada é recusado pela análise longitudinal.

Ou seja: "quem no laboratório confirmou que não rotaciona, e quando"
continua sem resposta real, e `docs/definicoes-metricas.md` §6.1 deve
continuar registrando isso como **não preenchido**, não como resolvido.
O que muda é que essa lacuna **não bloqueia nem distorce** o pipeline: se
a suposição da equipe estiver errada, basta que quem carregar os vídeos
reais informe a rotação verdadeira trial a trial.

> **Complemento (12/11/2026): duas correções de fato.**
>
> - **A CLI assume 0°.** O banco não tem DEFAULT, mas `barnes video load` tem:
>   `--rotation-deg` vale `0.0` quando omitido (`src/barnes/cli.py:245`). Quem
>   carrega um vídeo sem a opção grava 0° sem ter declarado nada. A suposição da
>   equipe está, portanto, no padrão da CLI, e é isso que precisa estar
>   documentado como suposição. Tornar a opção obrigatória quebraria o roteiro
>   de demonstração e não é necessário.
> - **A atribuição da resposta.** Dois lugares dizem que a resposta veio do
>   laboratório: o §6.1 de `docs/definicoes-metricas.md` ("Resposta: **Não.** O
>   LNBio não rotaciona a plataforma.") e o texto de ajuda do `--rotation-deg`
>   ("porque o LNBio não rotaciona a plataforma (resposta B4)"). Os dois passaram
>   a dizer "**suposição da equipe**" em 12/11/2026, mantendo "respondido por /
>   data" não preenchidos (seção 17).
> - **Como perceber uma rotação real:** as marcas de desgaste da seção 1 mudando
>   de posição em relação aos elementos fixos da borda do quadro, entre trials.

## 14. Protocolo de referência e quem decide (C5, C6)

**Decisão:**

- **C5:** adotar Sunyer et al. (2007) como protocolo de referência do método e
  Harrison et al. (2006) para as estratégias, conferindo as citações antes do
  relatório.
- **C6:** sem contato, não há quem assine pelo laboratório. Quem aprova este
  documento é a equipe (aprovação de 12/11/2026: Lucas). O relatório
  declara que **G3 não foi fechado** e que os critérios de aceite que dependem
  do laboratório (US-12, US-13, US-18, US-21, US-25 cenário 2) ficam como
  limitação externa.

Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas)

## 15. Dados, infraestrutura e tratamento da pose

**Decisão:**

- **Trials representativos (A1/G1):** a equipe escolhe 3 entre os vídeos que
  já tem — um do primeiro dia, um de dia avançado e um probe — e registra a
  escolha (nome do arquivo e hash) em `docs/protocolo-anotacao.md`.
- **GPU (D2):** o treino continua nas máquinas da equipe (já é o plano da
  US-07); a GPU institucional deixa de ser pendência.
- **Operador (D1):** assumir pesquisador sem experiência de linha de comando;
  o manual e o roteiro da US-30 são escritos para esse perfil.
- **Tratamento da pose (US-10):** manter os valores propostos pelo grupo
  (lacuna curta de 5 quadros, mediana de 5 quadros, cobertura mínima 0,98),
  já registrados em `configs/default.yaml` como decisão da equipe.
- **Desenho do experimento (B1, B6):** o script indica 4 dias × 4 trials,
  2 probes e dois grupos (WT e mutante); a linha de referência em 9 nos
  gráficos de incidência sugere 9 animais por grupo. É indício, não
  confirmação.

Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas)

## 16. Como estas decisões entram no software

`configs/default.yaml` diz que os limiares do G3 só são preenchidos depois de
`docs/definicoes-metricas.md` assinado. Sem laboratório, isso não vai
acontecer, e B5 e C3 travam US-16 e US-17 indefinidamente. A equipe precisa
escolher uma das duas saídas:

- **(a) Manter `null`.** As histórias ficam implementadas e testadas, mas não
  produzem `primary_event`/`total_event` nem contagem de erros com os dados
  reais; o `trials.csv` da US-25 não sai completo.
- **(b) Preencher com os valores aprovados aqui, marcados como decisão da
  equipe** — como já é feito com `encontrar` (C1, "PROVISÓRIO") e com as
  seções `pose`/`anotacao`: comentário em cada chave apontando para este
  documento, `versao_definicoes` indicando "decisões da equipe, sem G3", e
  `calibrado_contra_anotacao: false`. Toda saída leva essa marca, e o
  relatório declara a limitação.

Decidido em: 12/11/2026 · por: equipe (aprovado por Lucas) · opção: **(b)**, aplicada em `configs/default.yaml`

## 17. O que foi aplicado no repositório (12/11/2026)

- **`configs/default.yaml`** (opção b da seção 16):
  `versao_definicoes: decisoes-equipe-2026-11-12-sem-G3`;
  `entrar.raio_fator: 1.0` e `entrar.duracao_minima_s: 0.2` (seção 7);
  `erro.criterio: qualquer_buraco_incorreto` (seção 8);
  `trial.tempo_limite_s: 180` (seção 6);
  `estrategia.cruzamentos_centro_min: 1`, `erros_ate_alvo_max: 3` e
  `adjacencia_angular_graus: 18` (360/20 buracos; revisar na US-20 se a montagem
  tiver outro número de buracos) (seção 10). Ficam `null`, de propósito:
  `dwell.duracao_minima_s` (não é lido) e `estrategia.entropia_max_espacial`.
  `encontrar` (C1) continua com os valores provisórios de antes, e
  `calibrado_contra_anotacao` continua `false`. Cada chave aponta para a seção
  deste documento.
- **A marca nas saídas:** toda execução grava em `execucao.limiares` a cópia do
  YAML usado, inclusive `versao_definicoes`. Assim qualquer número produzido com
  estes valores é rastreável como "decisão da equipe, sem G3"
  (`barnes execution show <id>`).
- **`docs/definicoes-metricas.md`:** a tabela de limiares indica, linha a linha,
  "decisão da equipe (sem G3)"; §6.1 (B4) passa a dizer "suposição da equipe";
  as notas da US-17 e da US-18 apontam para este documento.
- **`src/barnes/cli.py`:** texto de ajuda do `--rotation-deg` sem atribuir a
  resposta ao LNBio.
- **`docs/CARDS.md`, `docs/revisao-cards.md`, `docs/manual-usuario.md`,
  `docs/ROTEIRO-DEMONSTRACAO.md`, `CLAUDE.md`:** pendências marcadas como
  decididas pela equipe, e a regra de distâncias em metros na exportação da
  US-25.
- **Não muda:** o código das métricas (US-13, US-16, US-17, US-18) continua em
  cm e lendo os valores do YAML; a conversão para metros é trabalho da US-25.

---

## Referências citadas

- Barnes, C.A. (1979). *Memory deficits associated with senescence: a
  neurophysiological and behavioral study in the rat.*
- Sunyer, B. et al. (2007). *Barnes maze, a useful task to assess spatial
  reference memory in mice.* Nature Protocols / Protocol Exchange.
- Harrison, F.E. et al. (2006, 2009). *Spatial and nonspatial escape
  strategies in the Barnes maze.* Learning & Memory.
- Illouz, T. et al. (2016). *Unraveling cognitive traits using the Barnes
  maze unveils complex strategies.* Scientific Reports.
- Attar, E.T. et al. (2013). Automated Barnes maze tracking protocol. PLoS
  ONE.
- `barnes_maze.py` — script de análise do laboratório, na raiz de
  `Gerenciamento_projetos` (fora deste repositório); fonte das evidências das
  seções 3, 4, 6, 11 e 15.

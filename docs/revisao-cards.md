# Epico A
vamos usar postgresql ao invés de SQLite
## [US-01]
- Não necessário criar algoritmo para lidar com fps variável, avisar talvez seja interessante porém é um caso específico de erro, deixar para o usuário resolver (fazer outro video ou alguma coisa) podemos fazer ao final do projeto se sobrar tempo
- Podemos começar com suporte somente para mp4

- Desconsiderar cenário 2 ou mudar a forma que está descrito

#### tarefas
- [ ] Implementar o leitor de vídeo em `src/barnes/io/` com OpenCV/FFmpeg
- [ ] Implementar a medição de fps real 
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


### [US-02] Calibração da escala px→cm por dois segmentos conhecidos (ou 4 pontos)
#### Regras de Negócio & Escopo
- [RN01] O pesquisador marca dois segmentos sobre um quadro de referência e informa a distância real entre eles, em centímetros.
- [RN02] O fator de escala (cm/px) é salvo no banco de dados, dessa forma pode ser utilizado para todos os vídeos com a mesma orientação de câmera
- [RN03] Sem escala calibrada, o sistema recusa o cálculo de qualquer métrica com unidade métrica (distância, velocidade, eficiência de rota).
- [RN04] O erro de medição aceito é **< 3%** contra uma distância real independente da usada na calibração (critério da seção 10).
- [RN05] Recalibrar sobrescreve a escala da montagem e invalida as métricas já calculadas com a escala anterior — as execuções antigas permanecem no banco, marcadas com a escala que usaram.

#### Tarefas
- [ ] Definir o formato do bloco de escala no YAML de montagem
- [ ] Implementar a marcação interativa de dois segmentos em janela OpenCV
- [ ] Implementar o cálculo do fator cm/px e sua gravação na montagem
- [ ] Implementar o bloqueio de métricas métricas quando não há escala calibrada
- [ ] Escrever teste verificando erro < 3% contra distância independente
- [ ] Implementar a marcação das execuções antigas com a escala que usaram
- [ ] Registrar no manual o procedimento de calibração e de recalibração

#### Definição de Pronto (DoD Específica do Card)
- [ ] Rotina de calibração interativa (janela OpenCV) implementada
- [ ] Escala persistida no banco de dados
- [ ] Teste automatizado verificando o erro < 3% em imagem sintética de escala conhecida
- [ ] Bloqueio de métricas métricas sem escala coberto por teste
- [ ] Procedimento descrito em `docs/manual-usuario.md`

### [US-03] Recorte do intervalo útil do trial
#### Regras de Negócio & Escopo
- [RN01] Início e fim do intervalo são configuráveis por trial, em segundos o
- [RN02] **Nenhuma** métrica, evento ou ponto de trajetória é calculado fora do intervalo útil.
- [RN03] O instante de início (evento **S**, soltura) é detectado automaticamente quando possível — por exemplo, pela remoção do cilindro ou pelo primeiro movimento do animal — e sempre pode ser corrigido manualmente.
- [RN04] O intervalo efetivamente usado é persistido no registro do trial e reportado nas saídas, para auditoria.
- [RN05] O tempo zero de todas as latências é o início do intervalo útil, não o início do arquivo de vídeo.

# Epico B
[us-04]


Entender o uso do YAML, ver se é possível substituir pelo banco de dados

Decisão: substituído por Postgres. Sem YAML de montagem — `maze_configs` +
`holes` (já existentes desde o schema inicial, US-01) cobrem centro/raio/N
/ângulo (via `holes[0].angle_deg`)/alvo (via `holes.is_target`); zonas de
proximidade são derivadas em memória via Shapely quando necessárias, não
persistidas. `configs/montagens/*.yaml` removido (ver
`configs/montagens/README.md`). "Ângulo inicial" não ganhou coluna própria:
é `holes[0].angle_deg`, derivável, não um dado independente. "Montagem real
do LNBio" agora é `database/seeds/lnbio_barnes.py` (rodar com
`uv run python -m database.seeds.lnbio_barnes`), ainda com valores
pendentes de B2 — mesma pendência que já existia no YAML (todo `null`).

[US-05]
Minha preocupação nessa não é necessariamente a rotação da plataforma mas a mudança do ângulo/posição da câmera, como os vídeos são feitos em dias diferentes, as vezes a camera fica deslocada, podendo ter a necessidade de recalibrar o vídeo

Decisão: B4 respondida como "o LNBio não rotaciona a plataforma". Pela RN04,
a rotação é gravada como 0° em todo trial (`video load --rotation-deg`,
padrão 0, gravado explicitamente) e a conversão vira identidade. A coluna
`trials.rotation_deg` (migração `0004`, sem DEFAULT; NULL = não registrada =
análise recusada) e o código permanecem. Para a câmera deslocada: como a
câmera só vê a plataforma de cima, não há marco de parede; como a
plataforma não gira, a âncora do referencial da sala é um **buraco físico
de referência** combinado com o lab, que é sempre o buraco 0 da montagem.
Câmera mexeu = nova montagem arrastando até o mesmo buraco; os ângulos de
sala continuam comparáveis. Sem coluna nova em `maze_configs`. Conversões em
`src/barnes/geometry/reference_frame.py`; comandos `barnes trial
set-rotation` e `barnes trial show`. Referenciais documentados em
`docs/definicoes-metricas.md`, seção 6. Pendente com o lab: qual é o buraco
de referência.

# Epico C
[US-06]
Ver se realmente é necessário treinar modelo SLEAP, talvez exista forma mais simples de fazer isso, mas vamos deixar assim por enquanto
podemos ver de usar o YOLO-pose, e adaptamos para a licença AGPL

Existe uma GPU instituicional, porém, ver se há necessidade de usa-la

> não tenho tanto conhecimento do épico C e D, podemos ir alterando detalhes ao decorrer do projeto

## US-07/US-08 — implementação de outubro de 2026

Escopo atualizado pelo solicitante: treino primeiro nas máquinas do grupo,
NVIDIA >=4 GiB/16 GB de RAM; fallback instituição, Kaggle e Colab nessa ordem.
Nuvem exige D4 favorável registrado e somente quadros rotulados. O código não
executa uploads. A opção escolhida é SLEAP-NN 0.3.1/PyTorch (sem YOLO/AGPL);
versões fixadas em `pyproject.toml`/`uv.lock` e configuração por montagem.

Foi acrescentada `execucao` no PostgreSQL para proveniência das tentativas de
pose, preservando a relação 1:1 de `trial_results`. US-27 continua responsável
pela proveniência completa de eventos/métricas futuros. Ver o
[guia US-07/US-08](pose-treino-avaliacao.md) para comandos e critérios.

Na avaliação, corpo é a distância focinho-base da cauda anotada por quadro.
São exigidos erro mediano <0,5 corpo por ponto/global/região e cobertura completa;
borda reprovada gera solicitação local de novos trials anotados em US-06,
sem reciclar o conjunto de teste. Essa definição operacional está documentada
para revisão pela equipe/laboratório. Ferramental implementado não equivale
a modelo real treinado ou validação offline física concluída.


## US-27 — proveniência e catálogo (outubro de 2026)

Decisões que estreitam o card (detalhes em [DER](DER.md) e no
[manual](manual-usuario.md) §2.2 e §4.5):

- **Nomes de tabela mantidos.** O card lista `animal`, `montagem`, `sessao`,
  `trial`, `metrica`; o banco já tinha `subjects`, `maze_configs`, `trials`,
  `trial_results`. Renomear quebraria bancos em uso — a correspondência fica
  documentada no DER. Só o que é novo nasce em português (`evento_buraco`,
  `sessao`), como `execucao`.
- **`sessao` é uma VIEW** derivada de `trials` (animal, `day_number`, `phase`,
  data do primeiro carregamento), sem tabela própria nem backfill.
- **Métrica com histórico.** O escopo pede "uma linha por trial, por
  execução": `trial_results` deixou de ser 1:1 por trial (decisão provisória da
  US-02/US-07). Reprocessar acrescenta; o resultado atual é o mais recente.
- **`execucao` estendida, não recriada:** `kind = 'processamento'`, commit,
  estado sujo, limiares, parâmetros e hash do vídeo em colunas próprias.
  Métricas anteriores à US-27 receberam uma execução "legado" na migração.
- **Conexão:** mantido `BARNES_DATABASE_URL` (agora também lido de `.env`);
  testes usam um banco separado, `BARNES_TEST_DATABASE_URL`.
- **Distribuição do PostgreSQL para o laboratório (SCRUM-148): em aberto.**
  Três opções (nativo, Docker, voltar para SQLite) com prós e contras no manual,
  §2.2.2, para decisão da equipe/cliente.

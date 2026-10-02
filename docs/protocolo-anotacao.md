# Protocolo de anotação de pose

**US-06 · Sprint 1 · status: ferramental pronto — aguardando a rodada de anotação**

Como os quadros são amostrados, rotulados e divididos para treinar o modelo de
pose (US-07) e para medir seu erro por região (US-08).

Os parâmetros numéricos deste protocolo ficam na seção `anotacao` de
`configs/default.yaml`, nunca no código. Diferente dos limiares de métrica
(portão G3), eles são **decisão da equipe**: definem só quais quadros são
anotados, não o que o laboratório chama de latência ou de erro. Os valores
abaixo são a proposta inicial do grupo; mudar o protocolo é mudar o YAML e
atualizar esta página.

## 1. Pontos anotados

Três pontos, animal único, **sempre nesta ordem** (RN01). É também a ordem e o
nome exato dos nós do esqueleto no SLEAP, e o importador recusa um esqueleto
com outros nomes:

| Ordem | Nó no SLEAP | Ponto | Definição | Observação |
|---|---|---|---|---|
| 1 | `focinho` | Focinho | Ponta do nariz | Define os eventos de buraco — o mais crítico |
| 2 | `centro_corpo` | Centro do corpo | Ponto médio do dorso, a meio caminho entre a nuca e a base da cauda | Base do eixo de orientação; define a região do quadro na contagem |
| 3 | `base_cauda` | Base da cauda | Onde a cauda sai do corpo | |

A orientação da cabeça θ é derivada do eixo **centro → focinho** (US-09).

**Ponto não visível:** se o focinho estiver de fato encoberto (dentro do
buraco, por exemplo), marque a posição estimada. O conjunto só é aceito com
os três pontos em todo quadro (Cenário 1); `barnes pose import-slp` lista os
quadros com ponto faltando.

## 2. Amostragem de quadros

A amostragem cobre as três regiões, **não** quadros aleatórios: o erro do modelo
é reportado separadamente por região em US-08, e a perda de pose junto à borda
(sombra e oclusão do focinho) acontece exatamente onde os eventos ocorrem.

`barnes pose sample` escolhe os quadros automaticamente:

1. **Intervalo útil (US-03):** só quadros entre a soltura e o fim do trial. A
   mão do operador soltando o animal não entra no conjunto.
2. **Posição aproximada do animal:** ainda não existe modelo, então ela vem de
   segmentação por contraste. O fundo é a mediana de 25 quadros do trial, e o
   animal é a maior região que difere desse fundo dentro da plataforma.
3. **Região**, pela geometria da montagem (US-04), com a regra abaixo.
4. **Sorteio por região**, com semente fixa e espaçamento mínimo entre quadros
   (quadros vizinhos são quase idênticos e não acrescentam nada ao treino).

| Região | Regra (`anotacao.regioes`) | Quadros por trial | Por quê |
|---|---|---|---|
| Proximidade dos buracos | até `buraco_margem_raios` = **1,0** raio de buraco além da borda do buraco | **40** | Onde os eventos acontecem; tem prioridade sobre as outras |
| Centro da plataforma | até `centro_raio_frac` = **0,5** do raio da circunferência dos buracos | **30** | |
| Borda | todo o resto, inclusive além da circunferência dos buracos | **30** | Principal causa de perda de pose |

Espaçamento mínimo: `intervalo_minimo_quadros` = **25** quadros (1 s a 25 fps).
Semente: `semente` = **0**.

Total-alvo: cerca de 100 quadros por trial. Com os 3 trials representativos
de G1, são cerca de 300 quadros, a dimensão prevista para um animal com três
pontos.

A região usada **na escolha** é só uma estimativa. A **contagem reportada**
(Cenário 2) usa o `centro_corpo` anotado à mão; ver a seção 7.

> **Dado para a revisão de abordagem (RN07a).** `barnes pose sample` imprime
> em quantos quadros a segmentação por contraste encontrou o animal. Se essa
> taxa for alta nos vídeos reais, é um primeiro indício de que talvez não seja
> preciso treinar modelo. Ainda assim, a orientação da cabeça exige o
> focinho, que a segmentação sozinha não dá.

## 3. Divisão treino / validação / teste

**Divisão por trial, nunca por quadro** (RN03). Quadros do mesmo trial são
quase idênticos entre si; dividir por quadro infla a métrica de teste.

| Conjunto | Proporção de **trials** (`anotacao.divisao`) | Trials | Quadros |
|---|---|---|---|
| Treino | 0,70 | _preencher após `pose split`_ | |
| Validação | 0,15 | | |
| Teste | 0,15 | | |

Com poucos trials, todo conjunto com proporção maior que zero recebe ao menos
um trial: com os 3 trials de G1, fica um em cada. O sorteio usa a mesma
`semente`, então a divisão é reprodutível. O resultado fica em
`data/annotations/divisao.csv` (`trial, quadro, conjunto`).

**Verificação de vazamento (Cenário 3):** `barnes pose split` já verifica, e
`barnes pose check-split` verifica de novo qualquer manifesto, inclusive um
editado à mão. Se um trial aparecer em mais de um conjunto, o comando falha,
aponta o trial e exige nova divisão.

**Identidade do trial:** um trial é identificado pelo hash do conteúdo do
vídeo (12 primeiros caracteres do SHA-256), a mesma regra de
`trials.content_hash` no banco. Assim, o mesmo vídeo copiado com outro nome
não escapa da verificação.

## 4. Ferramenta

A anotação usa a interface do próprio SLEAP (RN05); nenhuma ferramenta de
anotação própria foi construída. O código lê o projeto do SLEAP (`.slp`) com
`sleap-io` (BSD-3, sem CUDA, extra `anotacao`) e converte para um formato
interno (`data/annotations/anotacoes.csv`). O resto do pipeline só conhece o
formato interno.

> Sujeito à revisão de abordagem de pose do Sprint 1 (RN07). Se YOLO-pose for
> adotado (decisão do cliente, por causa da licença AGPL), muda só o
> conversor; amostragem, divisão, verificação e contagem continuam valendo.

## 5. Privacidade e D4

Nada sai das máquinas do grupo, nem vídeo, nem quadros rotulados (RN06).
`data/` está no `.gitignore`. O treino é local. Se o fallback para nuvem for
acionado, sobem **apenas os quadros rotulados**, nunca os trials, e só com
resposta explícita de D4.

| Pergunta D4 (restrição de uso e CEUA) | Resposta do cliente | Data | Registrado por |
|---|---|---|---|
| Podemos usar quadros dos vídeos no relatório e na apresentação? | _pendente_ | | |
| Há restrição de CEUA sobre as gravações? | _pendente_ | | |

## 6. Como rodar

Pré-requisitos: `uv sync --extra anotacao`, Postgres local com a montagem
cadastrada (`barnes maze create`, US-04) e os vídeos em `data/raw/`.

```bash
# 1. Para cada trial: escolher e exportar os quadros
uv run barnes pose sample --video data/raw/<trial>.mp4 --maze-config-id <id>
#    → data/annotations/<trial>/quadros/quadro_NNNNNN.png + amostragem.csv
#    (o intervalo útil é detectado; corrija com --start-frame/--end-frame se precisar)
#    amostragem.csv registra a montagem usada, que o passo 5 reaproveita por trial

# 2. No SLEAP: novo projeto → importar as pastas quadros/ como imagens →
#    esqueleto com os nós focinho, centro_corpo, base_cauda (nesta ordem) →
#    anotar → salvar data/annotations/projeto.slp
#    Salvar como .slp comum: projeto com imagens embutidas (.pkg.slp) é recusado
#    pelo import-slp, porque perde a referência ao trial de cada quadro

# 3. Converter para o formato interno (exige os três pontos em todo quadro).
#    Aceita vários .slp de uma vez (um por anotador); quadro repetido entre eles é erro.
uv run barnes pose import-slp data/annotations/*.slp

# 4. Dividir por trial e verificar vazamento
uv run barnes pose split

# 5. Contar os quadros por região e colar o resultado na seção 7.
#    Cada trial é classificado com a montagem registrada na sua amostragem
#    (trials de dias diferentes podem ter a câmera deslocada). --maze-config-id
#    só preenche trials sem registro e é recusado se contradisser um registro.
uv run barnes pose report

# A qualquer momento, reverificar a divisão
uv run barnes pose check-split
```

## 7. Registro das rodadas

| Rodada | Data | Anotador(es) | Quadros | Centro | Borda | Buraco | Versão do conjunto |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

Divisão do trabalho (sugestão, a confirmar pela equipe): cada integrante
anota um ou mais trials inteiros (pastas `<trial>/quadros/`) no seu próprio
`.slp`, e `import-slp` junta todos. Assim cada trial tem um anotador
consistente e não há conflito de edição no mesmo arquivo.

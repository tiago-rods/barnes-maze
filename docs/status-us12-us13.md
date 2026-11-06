# Entrega técnica US-12/US-13 — atualização em 06/11/2026

Branch `US-12_13/Tales`, criada da `origin/main` em `cf94dc2`, sem conflitos.
Este relatório separa implementação do software de validação experimental e
aceite do cliente. Nenhum dado do laboratório foi enviado para fora da máquina.

## US-12

| Ticket | O que existe | O que falta para concluir a atividade real |
|---|---|---|
| SCRUM-160 | Bloqueio D3 documentado; comando registra bloqueio sem improvisar referência | Confirmar entrega, observador, trial e data acordada com o laboratório |
| SCRUM-161 | Leitura validada de D3 e comparação por evento, com erros assinados/absolutos, faltas e extras | Executar com a anotação real |
| SCRUM-162 | Reexecução por YAML, histórico JSON/Markdown e proveniência de cada rodada | Testar as combinações acordadas com o laboratório |
| SCRUM-163 | Tolerância inclusiva de 0,5 s por descoberta implementada e testada | Comprovar no trial de referência real |
| SCRUM-164 | Documento atualizado e comando para incorporar evidência/limiares de uma rodada | Selecionar limiares finais e anexar a evidência real |
| SCRUM-165 | Evidência local preparada para revisão; G3 permanece explicitamente pendente | Submeter ao decisor e receber aceite escrito, ou registrar a divergência discutida |

**US-12 não está aceita:** D3 não está disponível/confirmada nesta sessão. Não
houve calibração real nem afirmação de que a tolerância foi atingida. A entrega
atual é o ferramental testado para executar a calibração quando D3 chegar.

## US-13

| Ticket | Implementação | Dependência externa |
|---|---|---|
| SCRUM-167 | Critério operacional proposto documentado | Confirmar área, duração e convenção de tempo com C2/G3 |
| SCRUM-168 | `entrar.raio_fator`, `duracao_minima_s`, `focinho_dentro`; valores pendentes recusados | Preencher os dois valores numéricos confirmados; permanecem `null` |
| SCRUM-169 | Focinho dentro do círculo calibrado, inclusive fronteira | Validar a área no protocolo do laboratório |
| SCRUM-170 | Duração contínua, interrupção por lacunas/saídas e reentradas | Validar a duração e o instante de referência de E |
| SCRUM-171 | Hesitação em segundos e caminho do centro em cm; CSV/JSON; primeiro E do alvo fornece totais | Validar com trajetórias reais; exportação estatística completa é US-25 |
| SCRUM-172 | Entrada sem D ou com D posterior é preservada e sinalizada por trial/buraco; deltas ausentes | Revisar eventuais inconsistências reais |
| SCRUM-173 | Comparação por entrada com tolerância inclusiva de 0,3 s, sem média que esconda desvios | Executar contra a anotação real de entrada |
| SCRUM-174 | Critérios e limitações documentados nas definições e no guia de operação | Aceite escrito do laboratório |

**Software da US-13 implementado; aceite experimental pendente.** Os testes
sintéticos não comprovam o erro de 0,3 s no laboratório. Também não definem os
valores C2/G3 de produção.

## Integração e verificação

- Comandos `events enter`, `events calibrate` e `events calibration-evidence`.
- Algoritmo `events/discovery.py` da US-11 preservado.
- Eventos e `execucao` gravados juntos; detalhes em JSONB na migração `0009`.
- Relatórios com marca de qualidade de pose, hashes, parâmetros e origem da série.
- Comparações e reexecução sobre o Parquet sem abertura/decodificação de vídeo.
- Testes do detector, comparação, histórico, CLI, exportação e falhas de escrita.
- Verificação inicial em 05/11/2026: suíte completa com **794 testes aprovados e 124
  pulados**. Dos pulados, 121 dependem do PostgreSQL de teste, dois do backend
  opcional SLEAP-NN e um de sockets AF_UNIX indisponíveis no ambiente. Ruff e
  `git diff --check` passaram.
- Atualização em 06/11/2026: PostgreSQL 16.15 preparado em ambiente local isolado,
  com banco descartável. Todas as dez migrações foram aplicadas, incluindo
  `0009_us13_entry_details.sql`; a segunda aplicação não encontrou pendências.
  A falta de banco para validar esta entrega técnica foi resolvida.
- Novos testes de CLI com PostgreSQL real verificam reentradas, hesitação e
  totais exportados, vínculo dos arquivos à execução, comparação D3 sintética
  nas duas tolerâncias, preservação de rodadas antigas, inconsistências D→E
  e rollback real diante de falha na escrita dos artefatos.
- Verificação final em **06/11/2026: 924 testes aprovados, zero falhas/erros e
  3 pulados**. Nenhum teste PostgreSQL ficou pulado. Restaram somente dois
  testes do backend opcional SLEAP-NN (US-07/08) e um de sockets AF_UNIX.
  Ruff e `git diff --check` passaram. Os testes não deixaram registros nas
  tabelas de usuários, trials, execuções ou eventos; o servidor isolado foi
  encerrado ao final. [Evidência técnica e reprodução](validacao-us12-us13-postgres.md).

A validação do banco usa exclusivamente dados sintéticos. Ela não altera o
status experimental de D3/C2/G3 nas tabelas acima. Não houve mudança nos limiares
de produção, submissão ao cliente nem aceite escrito nesta continuação.

Veja o [guia de operação](eventos-calibracao-entrada.md) para formato D3,
comandos, convenções e continuação da validação. As definições e o aceite ficam
em [definicoes-metricas.md](definicoes-metricas.md).

# Validação técnica US-12/US-13 em PostgreSQL — 06/11/2026

## Ambiente e isolamento

Foi preparado um PostgreSQL **16.15**, Windows x64, exclusivamente para testes,
sem instalar serviço do Windows nem configurar um banco do laboratório.
O processo escuta somente em `127.0.0.1:55432`, com autenticação SCRAM e senha
aleatória local. Banco utilizado: `barnes_us12_13_test`.

Os binários vieram do arquivo ZIP da EDB, indicado pela
[página oficial de downloads Windows do PostgreSQL](https://www.postgresql.org/download/windows/).
Artefato: `postgresql-16.15-5-windows-x64-binaries.zip`, 373254386 bytes.
SHA-256 do arquivo recebido:

```text
43bb45f173a6f08cf1d29a97a6d8deb119e8e8093a24c00d2d1001a0ccaa8281
```

O ambiente auxiliar, os logs e os relatórios JUnit ficam em
`.venv/pg-us12-13/`, ignorado pelo Git. A senha não faz parte desta documentação
nem dos commits. A variável `BARNES_TEST_DATABASE_URL` foi fornecida somente ao
processo dos testes; não foi criado `.env` nem alterado um DSN de trabalho.

## Migrações e cenários

Aplicadas as dez migrações do repositório, de `0001_create_schema.sql` a
`0009_us13_entry_details.sql` (há duas migrações numeradas `0002`). A coluna
`evento_buraco.details` foi confirmada como `jsonb`. Reexecutar `apply_migrations`
retornou lista vazia, confirmando a aplicação idempotente.

Os testes reais cobrem:

- Detecção e gravação de descoberta, entrada e reentradas a partir de Parquet.
- Confirmação da duração mínima e cálculo de hesitação em segundos/cm.
- Primeiro E do alvo como origem dos totais exportados.
- CSV/JSON associados ao `execucao_id` persistido, com qualidade da pose.
- Comparação de D3 **sintética**, incluindo igualdade no limite de 0,5/0,3 s e
  reprovação imediatamente acima dele.
- Histórico de novas execuções com limiares diferentes sem sobrescrever anteriores.
- Entrada sem descoberta anterior preservada com inconsistência e deltas nulos.
- Rollback de `execucao` e `evento_buraco` se a exportação de arquivos falhar.
- Compatibilidade das chamadas de descoberta existentes e restrições SQL/FKs.
- Recusa de trajetórias truncadas antes de gravar execuções ou eventos.

A revisão final também acrescentou regressões para tempos/FPS incompatíveis,
qualidade de pose de outra execução, metadados incompletos e relatórios de
calibração internamente incoerentes. As comparações são recalculadas antes de
salvar ou anexar evidência; isso não autentica D3 nem concede aceite G3.

## Reproduzir

Resultado da suíte completa após a revisão final: **954 casos coletados, 951 aprovados, 0 falhas,
0 erros e 3 pulados**. Não houve testes PostgreSQL pulados. Os três restantes
exigem SLEAP-NN (dois casos de US-07/08) ou AF_UNIX (um caso, indisponível no
ambiente). A verificação Ruff passou.

O JUnit da revisão está em `.venv/pg-us12-13/review-postgres.xml`; a execução
anterior, com 924 aprovados e 3 pulados, permanece em `full-postgres.xml` no
mesmo diretório. Ruff e a formatação dos arquivos Python alterados passaram.
A conferência final do
banco encontrou zero linhas em `users`, `trials`, `execucao` e `evento_buraco`,
confirmando a limpeza das fixtures. O servidor de teste foi encerrado após a
execução; não ficou serviço em segundo plano.

Usar PostgreSQL 16 e um banco **descartável**, configurar
`BARNES_TEST_DATABASE_URL` para ele e aplicar as migrações nesse mesmo banco.
As instruções Docker/nativo estão no manual do projeto. Em PowerShell:

```powershell
# BARNES_TEST_DATABASE_URL já deve apontar para o banco descartável.
uv run barnes db migrate --dsn $env:BARNES_TEST_DATABASE_URL
uv run --no-sync python -m pytest tests/events/ tests/db/test_hole_events.py
uv run --no-sync python -m pytest
uv run --no-sync python -m ruff check src/ tests/
```

O conftest da suíte redireciona `BARNES_DATABASE_URL` ao DSN de teste antes da
coleta. Nunca utilizar um banco com dados reais para essa execução.

## Limite desta evidência

A validação técnica resolve a pendência de integração com PostgreSQL. Nenhuma
fixture deste teste é uma anotação entregue pelo laboratório. A convergência
experimental, os limiares finais e o aceite escrito continuam dependendo de
D3 e C2/G3, conforme [o relatório por ticket](status-us12-us13.md).

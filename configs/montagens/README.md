# Montagens

Esta pasta guardava, até a US-04, um YAML por montagem
(`configs/montagens/*.yaml`) com centro, raio, número de buracos, ângulo
inicial, alvo e escala px→cm.

A US-04 substituiu esse formato por Postgres: as tabelas `maze_configs` e
`holes` (`database/migrations/0001_create_schema.sql`) guardam a mesma
informação, e `src/barnes/db/maze_configs.py` faz a leitura/escrita
(`barnes maze create` / `barnes maze show`). Ver a decisão registrada em
`docs/revisao-cards.md` (entrada `[us-04]`).

A montagem real do LNBio, que antes seria um arquivo aqui, agora é
`database/seeds/lnbio_barnes.py` (ainda com valores pendentes da pergunta
B2 do laboratório).

Esta pasta fica sem YAML de propósito — mantida só para este README, para
quem procurar pela pasta antiga vinda de outra branch.

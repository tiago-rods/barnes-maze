"""Wizard web + dashboard local — desvio deliberado do backlog de cards.

Fica fora de `src/barnes` de propósito (mesmo raciocínio de
`database/seeds/`, ver CLAUDE.md): depende de `barnes.*`, mas não é parte
do pacote instalável/console script. Roda via `uv run` a partir da raiz do
repositório, no mesmo venv ativado por `uv sync --extra web`.
"""

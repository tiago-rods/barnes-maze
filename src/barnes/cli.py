"""Interface de linha de comando do projeto Barnes Maze."""

from __future__ import annotations

import typer

from barnes.db.connection import apply_migrations, get_connection

app = typer.Typer()
db_app = typer.Typer(help="Comandos de banco de dados.")
app.add_typer(db_app, name="db")


@db_app.command("migrate")
def migrate(
    dsn: str = typer.Option(
        None, help="DSN do Postgres. Padrão: variável de ambiente BARNES_DATABASE_URL."
    ),
) -> None:
    """Aplica as migrações pendentes em database/migrations/."""
    with get_connection(dsn) as conn:
        applied = apply_migrations(conn)

    if applied:
        typer.echo(f"Migrações aplicadas: {', '.join(applied)}")
    else:
        typer.echo("Nenhuma migração pendente.")


if __name__ == "__main__":
    app()

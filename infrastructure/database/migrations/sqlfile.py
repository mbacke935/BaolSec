"""Exécution des fichiers SQL des migrations.

Le SQL est envoyé tel quel au pilote, sans paramètres : les « % » des fonctions format()
ne sont pas interprétés comme des marqueurs.
"""
from pathlib import Path

from alembic import op

SQL = Path(__file__).resolve().parents[1] / "sql"


def run(text: str) -> None:
    with op.get_bind().connection.dbapi_connection.cursor() as cur:
        cur.execute(text)


def run_file(name: str) -> None:
    run((SQL / name).read_text(encoding="utf-8"))

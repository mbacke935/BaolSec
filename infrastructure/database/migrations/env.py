"""Environnement Alembic : exécute les fichiers SQL de infrastructure/database/sql, un par schéma.

La table de suivi des versions est public.alembic_version.
"""
from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, pool

url = os.environ.get("DATABASE_ADMIN_URL")
if not url:
    raise SystemExit("DATABASE_ADMIN_URL manquant (ex. postgresql+psycopg://postgres:...@localhost:5432/baolsec)")
if url.startswith("postgresql://"):          # forme libpq acceptée : pilote psycopg 3
    url = "postgresql+psycopg://" + url[len("postgresql://"):]


def run() -> None:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()


run()

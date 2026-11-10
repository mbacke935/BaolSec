"""Schéma acces : rôles, utilisateurs, sessions, journal d'audit (C4).

Le SQL est dans infrastructure/database/sql/0001_acces.sql.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0001_acces.sql")


def downgrade() -> None:
    run("DROP SCHEMA acces CASCADE")

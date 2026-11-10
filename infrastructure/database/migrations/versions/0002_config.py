"""Schéma config : sources, identifiants, règles, paramètres (C4).

Le SQL est dans infrastructure/database/sql/0002_config.sql.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0002"
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0002_config.sql")


def downgrade() -> None:
    run("DROP SCHEMA config CASCADE")

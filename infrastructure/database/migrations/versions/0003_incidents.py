"""Schéma incidents : état des alertes, incidents, chronologie, commandes (C4).

Le SQL est dans infrastructure/database/sql/0003_incidents.sql.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0003"
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0003_incidents.sql")


def downgrade() -> None:
    run("DROP SCHEMA incidents CASCADE")

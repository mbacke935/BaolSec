"""Schéma couverture : état des sources, historique, volumes, règles affectées (C4).

Le SQL est dans infrastructure/database/sql/0004_couverture.sql.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0004"
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0004_couverture.sql")


def downgrade() -> None:
    run("DROP SCHEMA couverture CASCADE")

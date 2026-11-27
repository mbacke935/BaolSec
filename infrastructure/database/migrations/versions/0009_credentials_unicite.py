"""Unicité des jetons de source actifs (F-3).

Le SQL est dans infrastructure/database/sql/0009_credentials_unicite.sql.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0009_credentials_unicite.sql")


def downgrade() -> None:
    run("DROP INDEX IF EXISTS config.uq_source_credentials_secret_hash_active;")

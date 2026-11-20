"""Ajout de la description aux sources (correction du schéma C4)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0007_source_description.sql")


def downgrade() -> None:
    run("ALTER TABLE config.sources DROP COLUMN IF EXISTS description;")

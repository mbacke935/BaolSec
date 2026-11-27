"""Métadonnées descriptives des sources (hostname, ip_address, environment, tags, responsible).

Le SQL est dans infrastructure/database/sql/0008_sources_extend.sql.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0008_sources_extend.sql")


def downgrade() -> None:
    run("ALTER TABLE config.sources DROP COLUMN IF EXISTS responsible, DROP COLUMN IF EXISTS tags, DROP COLUMN IF EXISTS environment, DROP COLUMN IF EXISTS ip_address, DROP COLUMN IF EXISTS hostname;")

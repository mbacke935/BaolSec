"""Enchaînements d'activités de corrélation alignés sur C3 (table 7).

Le SQL est dans infrastructure/database/sql/0010_correlation_chains.sql.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0010_correlation_chains.sql")


def downgrade() -> None:
    run("""UPDATE config.settings
              SET value = '[["authentication", "authentication"], ["authentication", "process"], ["authentication", "network"], ["web", "process"]]'::jsonb
            WHERE key = 'correlation.activity_chains';""")

"""Table Outbox transactionnelle pour les incidents (C19).

Le SQL est dans infrastructure/database/sql/0006_incident_outbox.sql.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0006_incident_outbox.sql")


def downgrade() -> None:
    run("""
DROP TABLE IF EXISTS incidents.incident_outbox;
""")

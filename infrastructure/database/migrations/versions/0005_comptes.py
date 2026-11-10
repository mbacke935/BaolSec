"""Comptes PostgreSQL par service et droits (C4).

Le SQL est dans infrastructure/database/sql/0005_comptes.sql.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlfile import run, run_file  # noqa: E402

revision = "0005"
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_file("0005_comptes.sql")


def downgrade() -> None:
    # Retire les droits dans cette base seulement : les comptes sont communs à tout le serveur
    # (une autre base, par exemple celle des tests, peut les utiliser).
    run("""
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['svc_api', 'svc_passerelle', 'svc_normalisation', 'svc_detection', 'svc_incidents', 'svc_couverture'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('DROP OWNED BY %I', r);
    END IF;
  END LOOP;
END $$""")

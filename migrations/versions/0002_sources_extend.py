"""0002_sources_extend - Add hostname, ip_address, environment, tags, responsible to config.sources

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE config.sources
            ADD COLUMN IF NOT EXISTS hostname    TEXT,
            ADD COLUMN IF NOT EXISTS ip_address  INET,
            ADD COLUMN IF NOT EXISTS environment TEXT
                CHECK (environment IN ('production', 'staging', 'test', 'developpement')),
            ADD COLUMN IF NOT EXISTS tags        TEXT[] NOT NULL DEFAULT '{}',
            ADD COLUMN IF NOT EXISTS responsible TEXT;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE config.sources
            DROP COLUMN IF EXISTS responsible,
            DROP COLUMN IF EXISTS tags,
            DROP COLUMN IF EXISTS environment,
            DROP COLUMN IF EXISTS ip_address,
            DROP COLUMN IF EXISTS hostname;
    """)

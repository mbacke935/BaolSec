"""Migration 0001 — Schéma initial BaolSec (C4 modèle de données).

Crée tous les types énumérés et toutes les tables dans les 4 schémas :
  acces      : utilisateurs, rôles, audit
  config     : sources, règles, fenêtres
  incidents  : incidents, alertes, événements corrélés, timeline
  couverture : état de couverture des sources

Revision ID: 0001
Revises: —
Create Date: 2026-11-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions & schémas ───────────────────────────────────────────────────

    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE SCHEMA IF NOT EXISTS acces")
    op.execute("CREATE SCHEMA IF NOT EXISTS config")
    op.execute("CREATE SCHEMA IF NOT EXISTS incidents")
    op.execute("CREATE SCHEMA IF NOT EXISTS couverture")

    # ── Enum types ─────────────────────────────────────────────────────────────

    op.execute("""
        CREATE TYPE acces.user_role AS ENUM ('ADMIN', 'ANALYST')
    """)
    op.execute("""
        CREATE TYPE incidents.incident_state AS ENUM (
            'OUVERT', 'EN_COURS', 'RESOLU', 'CLOS', 'FAUX_POSITIF'
        )
    """)
    op.execute("""
        CREATE TYPE incidents.severity AS ENUM (
            'INFO', 'FAIBLE', 'MOYEN', 'ELEVE', 'CRITIQUE'
        )
    """)
    op.execute("""
        CREATE TYPE incidents.timeline_entry_type AS ENUM (
            'ALERTE', 'EVENEMENT', 'CHANGEMENT_ETAT', 'COMMENTAIRE', 'REGLE'
        )
    """)
    op.execute("""
        CREATE TYPE couverture.coverage_state_enum AS ENUM (
            'INCONNUE', 'ACTIVE', 'SILENCIEUSE', 'FLUX_INCOMPLET', 'DESACTIVEE'
        )
    """)

    # ── Schema acces ───────────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE acces.users (
            id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name     TEXT,
            role          acces.user_role NOT NULL DEFAULT 'ANALYST',
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE acces.audit_log (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id     UUID REFERENCES acces.users(id) ON DELETE SET NULL,
            action      TEXT NOT NULL,
            resource    TEXT,
            resource_id UUID,
            detail      JSONB,
            ip_address  INET,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ON acces.audit_log (user_id)")
    op.execute("CREATE INDEX ON acces.audit_log (created_at DESC)")

    # ── Schema config ──────────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE config.sources (
            id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name                 TEXT NOT NULL UNIQUE,
            description          TEXT,
            type                 TEXT NOT NULL,
            active               BOOLEAN NOT NULL DEFAULT TRUE,
            silence_threshold_s  INTEGER NOT NULL DEFAULT 300,
            config               JSONB NOT NULL DEFAULT '{}',
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE config.detection_rules (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            logic       JSONB NOT NULL,
            severity    incidents.severity NOT NULL DEFAULT 'MOYEN',
            enabled     BOOLEAN NOT NULL DEFAULT TRUE,
            version     INTEGER NOT NULL DEFAULT 1,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE config.time_windows (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            rule_id     UUID NOT NULL REFERENCES config.detection_rules(id) ON DELETE CASCADE,
            window_s    INTEGER NOT NULL,
            threshold   INTEGER NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ON config.time_windows (rule_id)")

    # ── Schema incidents ───────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE incidents.incidents (
            id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            title        TEXT NOT NULL,
            description  TEXT,
            state        incidents.incident_state NOT NULL DEFAULT 'OUVERT',
            severity     incidents.severity NOT NULL DEFAULT 'MOYEN',
            opened_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at    TIMESTAMPTZ,
            assigned_to  UUID REFERENCES acces.users(id) ON DELETE SET NULL,
            metadata     JSONB NOT NULL DEFAULT '{}',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ON incidents.incidents (state)")
    op.execute("CREATE INDEX ON incidents.incidents (severity)")
    op.execute("CREATE INDEX ON incidents.incidents (opened_at DESC)")

    op.execute("""
        CREATE TABLE incidents.alerts (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            incident_id UUID REFERENCES incidents.incidents(id) ON DELETE CASCADE,
            rule_id     UUID REFERENCES config.detection_rules(id) ON DELETE SET NULL,
            source_id   UUID REFERENCES config.sources(id) ON DELETE SET NULL,
            severity    incidents.severity NOT NULL DEFAULT 'MOYEN',
            title       TEXT NOT NULL,
            detail      JSONB NOT NULL DEFAULT '{}',
            fired_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ON incidents.alerts (incident_id)")
    op.execute("CREATE INDEX ON incidents.alerts (fired_at DESC)")
    op.execute("CREATE INDEX ON incidents.alerts (rule_id)")

    op.execute("""
        CREATE TABLE incidents.timeline (
            id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            incident_id UUID NOT NULL REFERENCES incidents.incidents(id) ON DELETE CASCADE,
            entry_type  incidents.timeline_entry_type NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            detail      JSONB NOT NULL DEFAULT '{}',
            source_id   UUID REFERENCES config.sources(id) ON DELETE SET NULL,
            alert_id    UUID REFERENCES incidents.alerts(id) ON DELETE SET NULL,
            user_id     UUID REFERENCES acces.users(id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ON incidents.timeline (incident_id)")
    op.execute("CREATE INDEX ON incidents.timeline (occurred_at DESC)")

    # ── Schema couverture ──────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE couverture.coverage_state (
            source_id         UUID PRIMARY KEY REFERENCES config.sources(id) ON DELETE CASCADE,
            state             couverture.coverage_state_enum NOT NULL DEFAULT 'INCONNUE',
            last_received_at  TIMESTAMPTZ,
            last_processed_at TIMESTAMPTZ,
            received_count    BIGINT NOT NULL DEFAULT 0,
            normalized_count  BIGINT NOT NULL DEFAULT 0,
            evaluated_at      TIMESTAMPTZ,
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE couverture.coverage_state_history (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            source_id       UUID NOT NULL REFERENCES config.sources(id) ON DELETE CASCADE,
            previous_state  couverture.coverage_state_enum,
            new_state       couverture.coverage_state_enum NOT NULL,
            reason          TEXT,
            changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ON couverture.coverage_state_history (source_id)")
    op.execute("CREATE INDEX ON couverture.coverage_state_history (changed_at DESC)")

    op.execute("""
        CREATE TABLE couverture.affected_rules (
            source_id UUID NOT NULL REFERENCES config.sources(id) ON DELETE CASCADE,
            rule_id   UUID NOT NULL REFERENCES config.detection_rules(id) ON DELETE CASCADE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (source_id, rule_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS couverture.affected_rules CASCADE")
    op.execute("DROP TABLE IF EXISTS couverture.coverage_state_history CASCADE")
    op.execute("DROP TABLE IF EXISTS couverture.coverage_state CASCADE")
    op.execute("DROP TABLE IF EXISTS incidents.timeline CASCADE")
    op.execute("DROP TABLE IF EXISTS incidents.alerts CASCADE")
    op.execute("DROP TABLE IF EXISTS incidents.incidents CASCADE")
    op.execute("DROP TABLE IF EXISTS config.time_windows CASCADE")
    op.execute("DROP TABLE IF EXISTS config.detection_rules CASCADE")
    op.execute("DROP TABLE IF EXISTS config.sources CASCADE")
    op.execute("DROP TABLE IF EXISTS acces.audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS acces.users CASCADE")
    op.execute("DROP TYPE IF EXISTS couverture.coverage_state_enum CASCADE")
    op.execute("DROP TYPE IF EXISTS incidents.timeline_entry_type CASCADE")
    op.execute("DROP TYPE IF EXISTS incidents.severity CASCADE")
    op.execute("DROP TYPE IF EXISTS incidents.incident_state CASCADE")
    op.execute("DROP TYPE IF EXISTS acces.user_role CASCADE")
    op.execute("DROP SCHEMA IF EXISTS couverture CASCADE")
    op.execute("DROP SCHEMA IF EXISTS incidents CASCADE")
    op.execute("DROP SCHEMA IF EXISTS config CASCADE")
    op.execute("DROP SCHEMA IF EXISTS acces CASCADE")

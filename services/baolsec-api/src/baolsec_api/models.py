"""Modèles Pydantic partagés pour l'API BaolSec (C20)."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"


# Rôles logiques de l'API (ADMIN/ANALYST, C5) ↔ noms stockés dans acces.roles
# (C4 §4.1 : « Administrateur », « Analyste »). Le mapping n'existe qu'à la
# frontière SQL : le JWT, le RBAC et le frontend ne manipulent que l'énum.
ROLE_DB_NAMES: dict[UserRole, str] = {
    UserRole.ADMIN: "Administrateur",
    UserRole.ANALYST: "Analyste",
}
ROLE_FROM_DB: dict[str, UserRole] = {name: role for role, name in ROLE_DB_NAMES.items()}


# Cycle de vie de l'incident (C4 §5.3, enum incidents.incident_status) : 3 états.
class IncidentState(str, Enum):
    OUVERT = "ouvert"
    EN_COURS = "en_cours"
    CLOS = "clos"


# État de triage d'une alerte (C4 §5.3, enum incidents.alert_status), distinct
# du document d'alerte immuable d'OpenSearch.
class AlertStatus(str, Enum):
    NOUVELLE = "nouvelle"
    EN_COURS = "en_cours"
    CLOTUREE = "cloturee"


class Severity(str, Enum):
    # Sévérité d'alerte/règle (C4/C5, enum config.severity) : 4 niveaux. Le niveau
    # « info » existe seulement pour la sévérité d'événement ECS (baolsec.severity.label),
    # jamais produit par les règles actuelles (C15).
    FAIBLE = "faible"
    MOYENNE = "moyenne"
    ELEVEE = "elevee"
    CRITIQUE = "critique"


class CoverageState(str, Enum):
    INCONNUE = "INCONNUE"
    ACTIVE = "ACTIVE"
    SILENCIEUSE = "SILENCIEUSE"
    FLUX_INCOMPLET = "FLUX_INCOMPLET"
    DESACTIVEE = "DESACTIVEE"


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenPayload(BaseModel):
    sub: str          # user_id (UUID as str)
    email: str
    role: UserRole
    exp: int


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Sources ───────────────────────────────────────────────────────────────────

class SourceConfig(BaseModel):
    transport: Literal["https", "syslog"] = "https"
    ingestion_mode: Literal["direct", "rejeu"] = "direct"
    host: str | None = None
    criticality: Literal["faible", "moyenne", "elevee", "critique"] | None = None
    expected_min_events_per_h: int | None = Field(None, ge=0)


class SourceConfigUpdate(BaseModel):
    transport: Literal["https", "syslog"] | None = None
    ingestion_mode: Literal["direct", "rejeu"] | None = None
    host: str | None = None
    criticality: Literal["faible", "moyenne", "elevee", "critique"] | None = None
    expected_min_events_per_h: int | None = Field(None, ge=0)


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    type: Literal["linux", "windows", "firewall", "http"]
    active: bool = True
    silence_threshold_s: int = Field(300, ge=1)
    config: SourceConfig = Field(default_factory=SourceConfig)


class SourceUpdate(BaseModel):
    description: str | None = None
    type: Literal["linux", "windows", "firewall", "http"] | None = None
    active: bool | None = None
    silence_threshold_s: int | None = Field(None, ge=1)
    config: SourceConfigUpdate | None = None


class SourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    type: str
    active: bool
    silence_threshold_s: int
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ── Règles ────────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    logic: dict[str, Any]
    severity: Severity = Severity.MOYENNE
    enabled: bool = True
    source_type: str | None = None
    threshold: int | None = Field(None, ge=1)
    window_id: uuid.UUID | None = None


class RuleUpdate(BaseModel):
    description: str | None = None
    logic: dict[str, Any] | None = None
    severity: Severity | None = None
    enabled: bool | None = None
    source_type: str | None = None
    threshold: int | None = Field(None, ge=1)
    window_id: uuid.UUID | None = None


class RuleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    logic: dict[str, Any]
    severity: Severity
    enabled: bool
    version: int
    created_at: datetime
    updated_at: datetime


# ── Incidents ─────────────────────────────────────────────────────────────────

class IncidentStateUpdate(BaseModel):
    state: IncidentState
    comment: str | None = None


class AlertResponse(BaseModel):
    # Le document d'alerte est immuable dans OpenSearch ; l'état de triage
    # (status, assignation) vient de incidents.alert_state (C4). alert_id est du texte.
    id: str
    rule_id: uuid.UUID
    severity: Severity
    status: AlertStatus
    assigned_to: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    title: str = ""
    detail: dict[str, Any] = {}
    fired_at: datetime


class IncidentResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    state: IncidentState
    severity: Severity
    opened_at: datetime
    closed_at: datetime | None
    assigned_to: uuid.UUID | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TimelineEntryResponse(BaseModel):
    id: int                       # incidents.incident_timeline.id (bigint identity)
    incident_id: uuid.UUID
    entry_type: str
    occurred_at: datetime
    summary: str = ""
    detail: dict[str, Any] = {}
    alert_id: str | None = None   # texte (déterministe)
    event_id: str | None = None
    user_id: uuid.UUID | None = None


# ── Couverture ────────────────────────────────────────────────────────────────

class CoverageStateResponse(BaseModel):
    source_id: uuid.UUID
    source_name: str
    state: CoverageState
    last_received_at: datetime | None
    last_processed_at: datetime | None
    received_count: int
    normalized_count: int
    evaluated_at: datetime | None


# ── Utilisateurs ──────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    # Identifiant unique de C4 (acces.users.username, NOT NULL). Si absent,
    # dérivé de la partie locale de l'email à la création.
    username: str | None = None
    role: UserRole = UserRole.ANALYST
    is_active: bool = True


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(None, min_length=8)


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str | None = None          # nullable dans acces.users (C4)
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None


# ── Pagination ────────────────────────────────────────────────────────────────

class Page(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Any]

"""Modèles Pydantic partagés pour l'API BaolSec (C20)."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

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


class IncidentState(str, Enum):
    OUVERT = "OUVERT"
    EN_COURS = "EN_COURS"
    RESOLU = "RESOLU"
    CLOS = "CLOS"
    FAUX_POSITIF = "FAUX_POSITIF"


class Severity(str, Enum):
    INFO = "INFO"
    FAIBLE = "FAIBLE"
    MOYEN = "MOYEN"
    ELEVE = "ELEVE"
    CRITIQUE = "CRITIQUE"


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

class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    type: str
    active: bool = True
    silence_threshold_s: int = Field(300, ge=0)
    config: dict[str, Any] = {}


class SourceUpdate(BaseModel):
    description: str | None = None
    type: str | None = None
    active: bool | None = None
    silence_threshold_s: int | None = Field(None, ge=0)
    config: dict[str, Any] | None = None


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
    severity: Severity = Severity.MOYEN
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
    id: uuid.UUID
    incident_id: uuid.UUID | None
    rule_id: uuid.UUID | None
    source_id: uuid.UUID | None
    severity: Severity
    title: str
    detail: dict[str, Any]
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
    id: uuid.UUID
    incident_id: uuid.UUID
    entry_type: str
    occurred_at: datetime
    detail: dict[str, Any]
    source_id: uuid.UUID | None
    alert_id: uuid.UUID | None
    user_id: uuid.UUID | None


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

/**
 * Types TypeScript correspondant aux modèles Pydantic de l'API BaolSec.
 */

export type UserRole = 'ADMIN' | 'ANALYST';

export type IncidentState =
  | 'OUVERT'
  | 'EN_COURS'
  | 'RESOLU'
  | 'CLOS'
  | 'FAUX_POSITIF';

export type Severity = 'INFO' | 'FAIBLE' | 'MOYEN' | 'ELEVE' | 'CRITIQUE';

export type CoverageStateEnum =
  | 'INCONNUE'
  | 'ACTIVE'
  | 'SILENCIEUSE'
  | 'FLUX_INCOMPLET'
  | 'DESACTIVEE';

// ── Sources ──────────────────────────────────────────────────────────────────

export interface Source {
  id: string;
  name: string;
  description: string | null;
  type: string;
  active: boolean;
  silence_threshold_s: number;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SourceCreate {
  name: string;
  description?: string;
  type: string;
  active?: boolean;
  silence_threshold_s?: number;
  config?: Record<string, unknown>;
}

export interface SourceUpdate {
  description?: string;
  type?: string;
  active?: boolean;
  silence_threshold_s?: number;
  config?: Record<string, unknown>;
}

// ── Règles ───────────────────────────────────────────────────────────────────

export interface Rule {
  id: string;
  name: string;
  description: string | null;
  logic: Record<string, unknown>;
  severity: Severity;
  enabled: boolean;
  source_type: string | null;
  threshold: number | null;
  window_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface RuleCreate {
  name: string;
  description?: string;
  logic: Record<string, unknown>;
  severity?: Severity;
  enabled?: boolean;
  source_type?: string;
  threshold?: number;
}

export interface RuleUpdate {
  description?: string;
  logic?: Record<string, unknown>;
  severity?: Severity;
  enabled?: boolean;
  source_type?: string;
  threshold?: number;
}

// ── Utilisateurs ─────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface UserCreate {
  email: string;
  password: string;
  role?: UserRole;
  is_active?: boolean;
}

export interface UserUpdate {
  role?: UserRole;
  is_active?: boolean;
  password?: string;
}

// ── Alertes ──────────────────────────────────────────────────────────────────

/** Aligné sur api/analyst.ts — champs réellement retournés par le backend */
export interface Alert {
  id: string;
  incident_id: string | null;
  rule_id: string | null;
  source_id: string | null;
  severity: Severity;
  title: string;
  detail: string | null;
  fired_at: string;
}

// ── Incidents ─────────────────────────────────────────────────────────────────

export interface Incident {
  id: string;
  title: string;
  description: string | null;
  severity: Severity;
  state: IncidentState;
  assigned_to: string | null;
  opened_at: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Aligné sur api/analyst.ts — champs réellement retournés par le backend */
export interface TimelineEntry {
  id: string;
  incident_id: string;
  entry_type: string;
  occurred_at: string;
  detail: string | null;
  source_id: string | null;
  alert_id: string | null;
  user_id: string | null;
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

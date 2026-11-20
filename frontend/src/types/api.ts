/**
 * Types TypeScript correspondant aux modèles Pydantic de l'API BaolSec.
 */

export type UserRole = 'ADMIN' | 'ANALYST';

// Cycle de vie de l'incident (C4 incidents.incident_status) : 3 états.
export type IncidentState = 'ouvert' | 'en_cours' | 'clos';

// État de triage d'une alerte (C4 incidents.alert_status).
export type AlertStatus = 'nouvelle' | 'en_cours' | 'cloturee';

// Sévérité d'alerte/règle (C4/C5 config.severity) : 4 niveaux. « info » n'existe
// que pour la sévérité d'événement ECS, jamais produite par les règles (C15).
export type Severity = 'faible' | 'moyenne' | 'elevee' | 'critique';

export type CoverageStateEnum =
  | 'INCONNUE'
  | 'ACTIVE'
  | 'SILENCIEUSE'
  | 'FLUX_INCOMPLET'
  | 'DESACTIVEE';

// ── Sources ──────────────────────────────────────────────────────────────────

export type SourceTransport = 'https' | 'syslog';
export type SourceIngestionMode = 'direct' | 'rejeu';
export type SourceCriticality = 'faible' | 'moyenne' | 'elevee' | 'critique';

export interface SourceConfig {
  transport: SourceTransport;
  ingestion_mode: SourceIngestionMode;
  host: string | null;
  criticality: SourceCriticality | null;
  expected_min_events_per_h: number | null;
}

export interface SourceConfigUpdate {
  transport?: SourceTransport;
  ingestion_mode?: SourceIngestionMode;
  host?: string | null;
  criticality?: SourceCriticality | null;
  expected_min_events_per_h?: number | null;
}

export interface Source {
  id: string;
  name: string;
  description: string | null;
  type: string;
  active: boolean;
  silence_threshold_s: number;
  config: SourceConfig;
  created_at: string;
  updated_at: string;
}

export interface SourceCreate {
  name: string;
  description?: string;
  type: string;
  active?: boolean;
  silence_threshold_s?: number;
  config?: SourceConfig;
}

export interface SourceUpdate {
  description?: string;
  type?: string;
  active?: boolean;
  silence_threshold_s?: number;
  config?: SourceConfigUpdate;
}

export interface SourceCredential {
  id: string;
  credential_type: 'token' | 'client_cert';
  cert_fingerprint: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface SourceCredentialRotation {
  credential_id: string;
  created_at: string;
  token: string;
  note: string;
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
  username: string;
  email: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface UserCreate {
  email: string;
  password: string;
  username?: string;
  role?: UserRole;
  is_active?: boolean;
}

export interface UserUpdate {
  role?: UserRole;
  is_active?: boolean;
  password?: string;
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

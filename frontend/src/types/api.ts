/**
 * Types de l'API BaolSec (C5, C20) — alignés sur les réponses réelles de baolsec-api.
 * Énumérations du schéma C4 : sévérités et états en minuscules françaises.
 */

export type UserRole = 'ADMIN' | 'ANALYST';
export type Severity = 'faible' | 'moyenne' | 'elevee' | 'critique';
export type IncidentState = 'ouvert' | 'en_cours' | 'clos';
export type AlertStatus = 'nouvelle' | 'en_cours' | 'cloturee';
export type CoverageStateName = 'INCONNUE' | 'ACTIVE' | 'SILENCIEUSE' | 'FLUX_INCOMPLET' | 'DESACTIVEE';
export type SourceType = 'linux' | 'windows' | 'firewall' | 'http';
export type Transport = 'https' | 'syslog';
export type Environment = 'production' | 'staging' | 'test' | 'developpement';

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface User {
  id: string;
  username: string;
  email: string | null;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  locked_until: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface UserCreate {
  email: string;
  username?: string;
  password: string;
  role: UserRole;
  is_active?: boolean;
}

export interface UserUpdate {
  username?: string;
  email?: string;
  role?: UserRole;
  is_active?: boolean;
  password?: string;
}

export interface SourceConfig {
  transport: Transport;
  ingestion_mode: 'direct' | 'rejeu';
  host: string | null;
  criticality: Severity | null;
  expected_min_events_per_h: number | null;
  hostname: string | null;
  ip_address: string | null;
  environment: Environment | null;
  tags: string[];
  responsible: string | null;
}

export interface Source {
  id: string;
  name: string;
  description: string | null;
  type: SourceType;
  active: boolean;
  silence_threshold_s: number;
  config: SourceConfig;
  created_at: string;
  updated_at: string;
}

export interface SourceCreate {
  name: string;
  description?: string | null;
  type: SourceType;
  active?: boolean;
  silence_threshold_s?: number;
  config?: Partial<SourceConfig>;
}

export type SourceUpdate = Partial<Omit<SourceCreate, 'name'>>;

export interface Credential {
  id: string;
  credential_type: 'token' | 'client_cert';
  cert_fingerprint: string | null;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface TokenCredential {
  credential_id: string;
  created_at: string;
  token: string;
  note: string;
}

export interface Rule {
  id: string;
  code: string | null;
  name: string;
  description: string | null;
  rule_type: 'simple' | 'window';
  category: string[];
  logic: Record<string, unknown>;
  severity: Severity;
  enabled: boolean;
  version: number;
  definition_yaml: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuleVersion {
  rule_id: string;
  version: number;
  checksum: string;
  definition_yaml: string;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
}

export interface Alert {
  id: string;
  rule_id: string;
  rule_code: string | null;
  severity: Severity;
  status: AlertStatus;
  assigned_to: string | null;
  assigned_to_name: string | null;
  incident_id: string | null;
  incident_title: string | null;
  title: string;
  detail: AlertEvidence | Record<string, unknown>;
  fired_at: string;
}

export interface AlertEvidence {
  available: boolean;
  found?: boolean;
  alert?: EcsDocument;
  events?: EcsDocument[];
}

export interface Incident {
  id: string;
  title: string;
  description: string | null;
  state: IncidentState;
  severity: Severity;
  opened_at: string;
  closed_at: string | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  alert_count: number;
  metadata: IncidentContext;
  created_at: string;
  updated_at: string;
}

export interface IncidentContext {
  users?: string[];
  hosts?: string[];
  source_ips?: string[];
  activity_families?: string[];
  rules?: string[];
  [key: string]: unknown;
}

export interface TimelineEntry {
  id: number;
  incident_id: string;
  entry_type: 'event' | 'alert' | 'status_change' | 'comment' | 'correlation' | 'conflict';
  occurred_at: string;
  summary: string;
  detail: Record<string, unknown>;
  alert_id: string | null;
  event_id: string | null;
  user_id: string | null;
  user_name: string | null;
}

export interface Comment {
  id: string;
  incident_id: string;
  author_id: string;
  author_name: string | null;
  body: string;
  created_at: string;
}

export interface CommandResult {
  contract: string;
  command_id: string;
  result: 'acceptee' | 'refusee' | 'en_erreur';
  completed_at: string;
  replayed: boolean;
  error?: { code: string; message: string };
}

export interface AffectedRule {
  rule_id: string;
  name: string;
  cause: 'silence' | 'flux_incomplet' | 'desactivee';
  since: string;
}

export interface Coverage {
  source_id: string;
  source_name: string;
  source_type: SourceType | null;
  state: CoverageStateName;
  state_since: string | null;
  last_received_at: string | null;
  last_processed_at: string | null;
  received_count: number;
  normalized_count: number;
  evaluated_at: string | null;
  silence_threshold_s: number | null;
  affected_rules: AffectedRule[];
}

export interface CoverageHistory {
  id: number;
  source_id: string;
  source_name: string;
  from_state: CoverageStateName;
  to_state: CoverageStateName;
  reason: string;
  changed_at: string;
}

/** Document ECS indexé (événement normalisé ou alerte) : seuls les champs affichés sont typés. */
export interface EcsDocument {
  _id?: string;
  _index?: string;
  '@timestamp'?: string;
  message?: string;
  event?: { id?: string; category?: string[]; type?: string[]; action?: string; outcome?: string; original?: string; dataset?: string; provider?: string };
  user?: { name?: string };
  host?: { name?: string };
  source?: { ip?: string; port?: number };
  destination?: { ip?: string; port?: number };
  rule?: { id?: string; name?: string };
  baolsec?: {
    source?: { id?: string; name?: string; type?: string };
    severity?: { label?: string; score?: number };
    received_at?: string;
    alert?: { event_ids?: string[]; group_key?: string; window_start?: string };
  };
  [key: string]: unknown;
}

export interface SearchPage {
  total: number;
  limit?: number;
  offset?: number;
  items?: EcsDocument[];
  hits?: EcsDocument[];
}

export interface AuditEntry {
  id: number;
  occurred_at: string;
  actor_id: string | null;
  actor_username: string;
  action: string;
  target_type: string;
  target_id: string;
  outcome: 'succes' | 'refus' | 'echec';
  details: Record<string, unknown> | null;
  client_ip: string | null;
}

export interface Setting {
  key: string;
  value: unknown;
  updated_at: string;
}

export interface Role {
  id: string;
  name: string;
  description: string | null;
  active_users: number;
  api_role: UserRole | null;
  permissions: string[];
}

export interface DlqEntry {
  seq: number;
  subject: string;
  service: string;
  reason_code: string | null;
  reason: string | null;
  original_stream: string | null;
  source_id: string | null;
  attempts: number | null;
  failed_at: string | null;
  message_id: string | null;
  payload_preview?: string | null;
  payload?: string | null;
  payload_encoding?: string | null;
  document?: Record<string, unknown>;
}

export interface DlqPage extends Page<DlqEntry> {
  by_subject: Record<string, number>;
}

export interface HealthComponent {
  name: string;
  kind: 'service' | 'donnees';
  status: 'up' | 'degraded' | 'down';
  latency_ms: number | null;
  detail: unknown;
}

export interface StreamStatus {
  stream: string;
  available: boolean;
  messages?: number;
  bytes?: number;
  consumers?: { name: string; pending: number; ack_pending: number; redelivered: number }[];
}

export interface PlatformHealth {
  status: 'up' | 'degraded' | 'down';
  checked_at: string;
  components: HealthComponent[];
  streams: StreamStatus[];
}

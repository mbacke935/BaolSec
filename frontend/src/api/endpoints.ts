/**
 * Accès aux ressources de l'API BaolSec (C5). Une fonction par route utilisée par l'interface.
 */
import { apiClient, getRefreshToken, idempotencyKey } from './client';
import type {
  Alert, AlertStatus, AuditEntry, CommandResult, Comment, Coverage, CoverageHistory, Credential,
  DlqEntry, DlqPage, EcsDocument, Incident, IncidentState, Page, PlatformHealth, Role, Rule,
  RuleVersion, SearchPage, Setting, Severity, Source, SourceCreate, SourceUpdate, TimelineEntry,
  TokenCredential, TokenResponse, User, UserCreate, UserUpdate,
} from '../types/api';

const data = <T,>(p: Promise<{ data: T }>) => p.then((r) => r.data);
const cmd = (url: string, body: unknown) =>
  data(apiClient.post<CommandResult>(url, body, { headers: { 'Idempotency-Key': idempotencyKey() } }));

// ── Authentification ─────────────────────────────────────────────────────────
export const auth = {
  login: (login: string, password: string) =>
    data(apiClient.post<TokenResponse>('/auth/login', new URLSearchParams({ username: login, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })),
  me: () => data(apiClient.get<User>('/auth/me')),
  logout: () => apiClient.post('/auth/logout', { refresh_token: getRefreshToken() ?? '' }).catch(() => undefined),
};

// ── Sources et identifiants ──────────────────────────────────────────────────
export const sources = {
  list: (params?: { active_only?: boolean; limit?: number; offset?: number }) =>
    data(apiClient.get<Page<Source>>('/sources', { params: { limit: 200, ...params } })),
  get: (id: string) => data(apiClient.get<Source>(`/sources/${id}`)),
  create: (body: SourceCreate) => data(apiClient.post<Source>('/sources', body)),
  update: (id: string, body: SourceUpdate) => data(apiClient.patch<Source>(`/sources/${id}`, body)),
  disable: (id: string) => apiClient.delete(`/sources/${id}`),
  enable: (id: string) => data(apiClient.patch<Source>(`/sources/${id}`, { active: true })),
  credentials: (id: string) => data(apiClient.get<Credential[]>(`/sources/${id}/credentials`)),
  newToken: (id: string) => data(apiClient.post<TokenCredential>(`/sources/${id}/credentials`)),
  addCertificate: (id: string, cert_fingerprint: string) =>
    data(apiClient.post<Credential & { credential_id: string }>(`/sources/${id}/credentials/cert`, { cert_fingerprint })),
  revoke: (id: string, credentialId: string) => apiClient.post(`/sources/${id}/credentials/${credentialId}/revoke`),
};

// ── Règles ───────────────────────────────────────────────────────────────────
export const rules = {
  list: (params?: { enabled_only?: boolean }) =>
    data(apiClient.get<Page<Rule>>('/rules', { params: { limit: 200, ...params } })),
  get: (id: string) => data(apiClient.get<Rule>(`/rules/${id}`)),
  create: (definition_yaml: string, enabled?: boolean) =>
    data(apiClient.post<Rule>('/rules', { definition_yaml, enabled })),
  update: (id: string, body: { definition_yaml?: string; enabled?: boolean }) =>
    data(apiClient.put<Rule>(`/rules/${id}`, body)),
  versions: (id: string) => data(apiClient.get<RuleVersion[]>(`/rules/${id}/versions`)),
  setEnabled: (id: string, enabled: boolean) => apiClient.post(`/rules/${id}/${enabled ? 'enable' : 'disable'}`),
};

// ── Utilisateurs, rôles, paramètres, audit, file de rejet ────────────────────
export const users = {
  list: () => data(apiClient.get<Page<User>>('/users', { params: { limit: 200 } })),
  create: (body: UserCreate) => data(apiClient.post<User>('/users', body)),
  update: (id: string, body: UserUpdate) => data(apiClient.patch<User>(`/users/${id}`, body)),
  deactivate: (id: string) => data(apiClient.post<User>(`/users/${id}/deactivate`)),
  reactivate: (id: string) => data(apiClient.post<User>(`/users/${id}/reactivate`)),
};

export const admin = {
  roles: () => data(apiClient.get<Role[]>('/roles')),
  settings: () => data(apiClient.get<Setting[]>('/settings')),
  setSetting: (key: string, value: unknown) => data(apiClient.patch<Setting>(`/settings/${key}`, { value })),
  audit: (params: { limit?: number; offset?: number; outcome?: string; action?: string; occurred_after?: string; domain?: string; actor?: string }) =>
    data(apiClient.get<Page<AuditEntry>>('/audit', { params })),
  dlq: (params: { limit?: number; offset?: number; service?: string; reason?: string }) =>
    data(apiClient.get<DlqPage>('/dlq', { params })),
  dlqEntry: (seq: number) => data(apiClient.get<DlqEntry>(`/dlq/${seq}`)),
};

// ── Alertes et incidents ─────────────────────────────────────────────────────
export const alerts = {
  list: (params?: { status?: AlertStatus; severity?: Severity; assigned_to_me?: boolean; limit?: number; offset?: number }) =>
    data(apiClient.get<Alert[]>('/alerts', { params: { limit: 100, ...params } })),
  get: (id: string) => data(apiClient.get<Alert>(`/alerts/${id}`)),
  setStatus: (id: string, status: AlertStatus) => cmd(`/alerts/${id}/status`, { status }),
  assign: (id: string, assignee_id: string | null) => cmd(`/alerts/${id}/assign`, { assignee_id }),
};

export const incidents = {
  list: (params?: { state?: IncidentState; severity?: Severity; active_only?: boolean; assigned_to_me?: boolean; limit?: number; offset?: number }) =>
    data(apiClient.get<Incident[]>('/incidents', { params: { limit: 100, ...params } })),
  get: (id: string) => data(apiClient.get<Incident>(`/incidents/${id}`)),
  timeline: (id: string) => data(apiClient.get<TimelineEntry[]>(`/incidents/${id}/timeline`)),
  alerts: (id: string) => data(apiClient.get<Alert[]>(`/incidents/${id}/alerts`)),
  comments: (id: string) => data(apiClient.get<Comment[]>(`/incidents/${id}/comments`)),
  setState: (id: string, state: IncidentState, comment?: string) => cmd(`/incidents/${id}/status`, { state, comment }),
  comment: (id: string, body: string) => cmd(`/incidents/${id}/comments`, { body }),
  assign: (id: string, assignee_id: string | null) => cmd(`/incidents/${id}/assign`, { assignee_id }),
  close: (id: string, reason?: string) => cmd(`/incidents/${id}/close`, { reason }),
  reopen: (id: string, reason?: string) => cmd(`/incidents/${id}/reopen`, { reason }),
};

// ── Couverture, recherche, supervision ───────────────────────────────────────
export const coverage = {
  list: () => data(apiClient.get<Page<Coverage>>('/coverage', { params: { limit: 500 } })),
  history: (source_id?: string) =>
    data(apiClient.get<CoverageHistory[]>('/coverage/history', { params: { limit: 100, source_id } })),
};

export interface EventFilters {
  q?: string;
  from?: string;
  to?: string;
  source_id?: string;
  user?: string;
  ip?: string;
  host?: string;
  category?: string;
  outcome?: string;
  limit?: number;
  offset?: number;
}

export const events = {
  search: (filters: EventFilters) => {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== '' && v !== undefined));
    return data(apiClient.get<SearchPage>('/events', { params }));
  },
  get: (id: string) => data(apiClient.get<EcsDocument>(`/events/${encodeURIComponent(id)}`)),
};

export const search = {
  lucene: (index: 'events' | 'alerts' | 'incidents', q: string, size = 50, from = 0) =>
    data(apiClient.post<SearchPage>(`/search/${index}`, { q, size, from })),
};

export const system = {
  health: () => data(apiClient.get<PlatformHealth>('/system/health')),
};

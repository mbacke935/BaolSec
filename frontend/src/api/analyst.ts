/**
 * API pour l'interface d'analyse (C23).
 * Réutilise les types de C22 et ajoute les endpoints d'analyse.
 */
import { apiClient } from './client';
import type { IncidentState, Severity, AlertStatus } from '../types/api';
// Réexport pour les pages d'analyse qui réutilisent ces types (C23).
export type { IncidentState, Severity, AlertStatus };

/** En-tête d'idempotence pour les commandes (C5 : l'API l'utilise comme command_id). */
function idem() {
  const key = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return { headers: { 'Idempotency-Key': key } };
}

// ── Incidents ─────────────────────────────────────────────────────────────────

export interface Incident {
  id: string;
  title: string;
  description: string | null;
  state: IncidentState;
  severity: Severity;
  opened_at: string;
  closed_at: string | null;
  assigned_to: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TimelineEntry {
  id: string;
  incident_id: string;
  entry_type: string;
  occurred_at: string;
  detail: Record<string, unknown>;
  source_id: string | null;
  alert_id: string | null;
  user_id: string | null;
}

export interface Alert {
  id: string;                       // alert_id (texte déterministe)
  rule_id: string;
  severity: Severity;
  status: AlertStatus;              // état de triage (incidents.alert_state)
  assigned_to: string | null;
  incident_id: string | null;
  title: string;
  detail: Record<string, unknown>;
  source_id?: string | null;        // non renvoyé par l'API (doc immuable OpenSearch)
  fired_at: string;
}

export interface CoverageState {
  source_id: string;
  source_name: string;
  state: string;
  last_received_at: string | null;
  last_processed_at: string | null;
  received_count: number;
  normalized_count: number;
  evaluated_at: string | null;
}

export interface SearchResult {
  total: number;
  hits: Array<Record<string, unknown>>;
}

// ── API calls ─────────────────────────────────────────────────────────────────

export const incidents = {
  list: (params?: { state?: IncidentState; limit?: number; offset?: number }) =>
    apiClient.get<Incident[]>('/incidents', { params }).then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Incident>(`/incidents/${id}`).then((r) => r.data),

  timeline: (id: string) =>
    apiClient.get<TimelineEntry[]>(`/incidents/${id}/timeline`).then((r) => r.data),

  alerts: (id: string) =>
    apiClient.get<Alert[]>(`/incidents/${id}/alerts`).then((r) => r.data),

  // Commandes (transmises au service Incidents, Analyste seul) avec Idempotency-Key.
  updateState: (id: string, state: IncidentState, comment?: string) =>
    apiClient.post(`/incidents/${id}/status`, { state, comment }, idem()).then((r) => r.data),

  assign: (id: string, assigned_to: string | null) =>
    apiClient.post(`/incidents/${id}/assign`, { assigned_to }, idem()).then((r) => r.data),

  comment: (id: string, body: string) =>
    apiClient.post(`/incidents/${id}/comment`, { body }, idem()).then((r) => r.data),
};

export const alerts = {
  list: (params?: { limit?: number; offset?: number; rule_id?: string; alert_status?: AlertStatus }) =>
    apiClient.get<Alert[]>('/alerts', { params }).then((r) => r.data),

  updateStatus: (id: string, status: AlertStatus) =>
    apiClient.post(`/alerts/${encodeURIComponent(id)}/status`, { status }, idem()).then((r) => r.data),

  assign: (id: string, assigned_to: string | null) =>
    apiClient.post(`/alerts/${encodeURIComponent(id)}/assign`, { assigned_to }, idem()).then((r) => r.data),
};

export const coverage = {
  list: () => apiClient.get<CoverageState[]>('/coverage').then((r) => r.data),
  history: () => apiClient.get('/coverage/history').then((r) => r.data),
};

export const search = {
  events: (q: string, size = 20) =>
    apiClient.post<SearchResult>('/search/events', { q, size }).then((r) => r.data),

  alerts: (q: string, size = 20) =>
    apiClient.post<SearchResult>('/search/alerts', { q, size }).then((r) => r.data),

  incidents: (q: string, size = 20) =>
    apiClient.post<SearchResult>('/search/incidents', { q, size }).then((r) => r.data),
};

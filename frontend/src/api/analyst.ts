/**
 * API pour l'interface d'analyse (C23).
 * Réutilise les types de C22 et ajoute les endpoints d'analyse.
 */
import { apiClient } from './client';
import type { IncidentState, Severity } from '../types/api';

/** Normalise une réponse API qui peut être un tableau direct ou {data:[]} / {items:[]} */
export function toList<T>(raw: unknown): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (Array.isArray((raw as any)?.data)) return (raw as any).data as T[];
  if (Array.isArray((raw as any)?.items)) return (raw as any).items as T[];
  return [];
}
// Réexport pour les pages d'analyse qui réutilisent ces types (C23).
export type { IncidentState, Severity };

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
  id: string;
  incident_id: string | null;
  rule_id: string | null;
  source_id: string | null;
  severity: Severity;
  title: string;
  detail: Record<string, unknown>;
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

  updateState: (id: string, state: IncidentState, comment?: string) =>
    apiClient.post<Incident>(`/incidents/${id}/status`, { state, comment }).then((r) => r.data),
};

export const alerts = {
  list: (params?: { limit?: number; offset?: number; rule_id?: string; source_id?: string }) =>
    apiClient.get<Alert[]>('/alerts', { params }).then((r) => r.data),
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

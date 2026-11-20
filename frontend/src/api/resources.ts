/**
 * Fonctions d'accès aux ressources de l'API BaolSec (C22).
 */
import { apiClient } from './client';
import type {
  Rule, RuleCreate, RuleUpdate,
  Source, SourceCreate, SourceUpdate,
  TokenResponse, User, UserCreate, UserUpdate,
  SourceCredential, SourceCredentialRotation,
} from '../types/api';

// ── Auth ─────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<TokenResponse> {
  const form = new URLSearchParams({ username: email, password });
  const { data } = await apiClient.post<TokenResponse>('/auth/login', form, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return data;
}

// ── Sources ──────────────────────────────────────────────────────────────────

export const sources = {
  list: (params?: { limit?: number; offset?: number; active_only?: boolean }) =>
    apiClient.get<Source[]>('/sources', { params }).then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Source>(`/sources/${id}`).then((r) => r.data),

  create: (body: SourceCreate) =>
    apiClient.post<Source>('/sources', body).then((r) => r.data),

  update: (id: string, body: SourceUpdate) =>
    apiClient.put<Source>(`/sources/${id}`, body).then((r) => r.data),

  disable: (id: string) =>
    apiClient.delete(`/sources/${id}`),

  credentials: (id: string) =>
    apiClient.get<SourceCredential[]>(`/sources/${id}/credentials`).then((r) => r.data),

  rotateCredential: (id: string) =>
    apiClient.post<SourceCredentialRotation>(`/sources/${id}/credentials/rotate`).then((r) => r.data),
};

// ── Règles ───────────────────────────────────────────────────────────────────

export const rules = {
  list: (params?: { limit?: number; offset?: number; enabled_only?: boolean }) =>
    apiClient.get<Rule[]>('/rules', { params }).then((r) => r.data),

  get: (id: string) =>
    apiClient.get<Rule>(`/rules/${id}`).then((r) => r.data),

  create: (body: RuleCreate) =>
    apiClient.post<Rule>('/rules', body).then((r) => r.data),

  update: (id: string, body: RuleUpdate) =>
    apiClient.put<Rule>(`/rules/${id}`, body).then((r) => r.data),

  disable: (id: string) =>
    apiClient.delete(`/rules/${id}`),
};

// ── Utilisateurs ─────────────────────────────────────────────────────────────

export const users = {
  list: (params?: { limit?: number; offset?: number; active_only?: boolean }) =>
    apiClient.get<User[]>('/users', { params }).then((r) => r.data),

  get: (id: string) =>
    apiClient.get<User>(`/users/${id}`).then((r) => r.data),

  me: () =>
    apiClient.get<User>('/users/me').then((r) => r.data),

  create: (body: UserCreate) =>
    apiClient.post<User>('/users', body).then((r) => r.data),

  update: (id: string, body: UserUpdate) =>
    apiClient.put<User>(`/users/${id}`, body).then((r) => r.data),

  disable: (id: string) =>
    apiClient.delete(`/users/${id}`),
};

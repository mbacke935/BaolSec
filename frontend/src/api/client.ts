/**
 * Client HTTP de l'API BaolSec.
 *
 * Conforme à C3 (fiche 4.6) : les jetons sont conservés en mémoire, jamais dans localStorage
 * (pas de vol de jeton par XSS). Recharger la page impose donc une reconnexion : c'est le
 * compromis de sécurité retenu. Le contrôle d'accès réel est fait par l'API à chaque requête.
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

let accessToken: string | null = null;
let refreshToken: string | null = null;
let onSessionExpired: (() => void) | null = null;

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 20_000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});

// Renouvellement du jeton d'accès : une seule tentative partagée entre les requêtes en attente.
let refreshing: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  if (!refreshToken) return null;
  try {
    const { data } = await axios.post<{ access_token: string; refresh_token: string }>(
      '/api/v1/auth/refresh',
      { refresh_token: refreshToken },
    );
    setTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
    const isAuthCall = original?.url?.includes('/auth/');
    if (error.response?.status === 401 && original && !original._retry && !isAuthCall) {
      original._retry = true;
      refreshing = refreshing ?? tryRefresh();
      const newToken = await refreshing;
      refreshing = null;
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(original);
      }
      clearTokens();
      onSessionExpired?.();
    }
    return Promise.reject(error);
  },
);

export function setTokens(access: string, refresh?: string): void {
  accessToken = access;
  if (refresh) refreshToken = refresh;
}
export function clearTokens(): void {
  accessToken = null;
  refreshToken = null;
}
export function getAccessToken(): string | null {
  return accessToken;
}
export function getRefreshToken(): string | null {
  return refreshToken;
}
export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler;
}

/** Message lisible à partir d'une erreur de l'API (détail FastAPI, RFC 9457 ou réseau). */
export function errorMessage(err: unknown, fallback = 'Une erreur est survenue.'): string {
  const e = err as AxiosError<{ detail?: unknown; title?: string }>;
  if (!e?.isAxiosError) return err instanceof Error ? err.message : fallback;
  if (!e.response) return "Le serveur ne répond pas : vérifiez votre connexion ou réessayez dans un instant.";
  const detail = e.response.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').join('.') : '';
        const msg = (d.msg ?? '').replace(/^Value error, /, '');
        return field ? `${field} : ${msg}` : msg;
      })
      .join(' · ');
  }
  if (detail && typeof detail === 'object') {
    const d = detail as { detail?: string; title?: string; message?: string };
    return d.detail ?? d.message ?? d.title ?? fallback;
  }
  const status = e.response.status;
  if (status === 403) return "Action non autorisée pour votre rôle.";
  if (status === 404) return 'Élément introuvable.';
  if (status === 429) return 'Trop de requêtes : patientez quelques secondes.';
  if (status >= 500) return 'Erreur du serveur : réessayez dans un instant.';
  return fallback;
}

/** Clé d'idempotence d'une commande (C5 §6) : un double clic n'applique la commande qu'une fois. */
export function idempotencyKey(): string {
  return crypto.randomUUID();
}

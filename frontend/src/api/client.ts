/**
 * Client Axios de l'API BaolSec.
 *
 * Conforme à C3 (fiche 4.6) : le jeton est conservé **en mémoire**, jamais dans
 * localStorage. Une actualisation de page impose donc une reconnexion — c'est le
 * compromis de sécurité retenu (pas de vol de jeton via XSS). Le contrôle d'accès
 * réel est effectué par l'API à chaque requête.
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

// Jetons en mémoire (perdus au rechargement de la page — voulu, C3).
let accessToken: string | null = null;
let refreshToken: string | null = null;

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  return config;
});

// Renouvellement du jeton d'accès (une tentative partagée à la fois).
let refreshing: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  if (!refreshToken) return null;
  try {
    const { data } = await axios.post<{ access_token: string; refresh_token: string }>(
      '/api/v1/auth/refresh',
      { refresh_token: refreshToken },
    );
    saveToken(data.access_token);
    saveRefreshToken(data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
    if (error.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      refreshing = refreshing ?? tryRefresh();
      const newToken = await refreshing;
      refreshing = null;
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(original);
      }
      clearToken();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  },
);

export function saveToken(token: string): void { accessToken = token; }
export function saveRefreshToken(token: string): void { refreshToken = token; }
export function clearToken(): void { accessToken = null; refreshToken = null; }
export function getToken(): string | null { return accessToken; }

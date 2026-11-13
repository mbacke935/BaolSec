/**
 * Client Axios configuré pour l'API BaolSec.
 * Injecte le JWT depuis localStorage et renouvelle le jeton d'accès sur 401
 * via le jeton de renouvellement (C3/C5 : jetons courts + refresh).
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

const TOKEN_KEY = 'baolsec_token';
const REFRESH_KEY = 'baolsec_refresh';

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
});

// Intercepteur requête : injecter le jeton d'accès
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Renouvellement du jeton d'accès (une tentative partagée à la fois)
let refreshing: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  const refresh = localStorage.getItem(REFRESH_KEY);
  if (!refresh) return null;
  try {
    // Appel direct (hors apiClient) pour ne pas déclencher cet intercepteur.
    const { data } = await axios.post<{ access_token: string; refresh_token: string }>(
      '/api/v1/auth/refresh',
      { refresh_token: refresh },
    );
    saveToken(data.access_token);
    saveRefreshToken(data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

// Intercepteur réponse : sur 401, tenter un refresh puis rejouer la requête
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
  }
);

export function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function saveRefreshToken(token: string): void {
  localStorage.setItem(REFRESH_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

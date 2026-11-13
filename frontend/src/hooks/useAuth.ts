/**
 * Hook d'authentification BaolSec (C22).
 * Gère login/logout + récupération du profil courant.
 */
import { useCallback, useEffect, useState } from 'react';
import { clearToken, getToken, saveRefreshToken, saveToken } from '../api/client';
import { login as apiLogin, users } from '../api/resources';
import type { User } from '../types/api';

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({ user: null, loading: true, error: null });

  const fetchMe = useCallback(async () => {
    if (!getToken()) {
      setState({ user: null, loading: false, error: null });
      return;
    }
    try {
      const user = await users.me();
      setState({ user, loading: false, error: null });
    } catch {
      clearToken();
      setState({ user: null, loading: false, error: null });
    }
  }, []);

  useEffect(() => { fetchMe(); }, [fetchMe]);

  const login = useCallback(async (email: string, password: string) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const { access_token, refresh_token } = await apiLogin(email, password);
      saveToken(access_token);
      saveRefreshToken(refresh_token);
      await fetchMe();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Erreur de connexion';
      setState({ user: null, loading: false, error: msg });
      throw err;
    }
  }, [fetchMe]);

  const logout = useCallback(() => {
    clearToken();
    setState({ user: null, loading: false, error: null });
    window.location.href = '/login';
  }, []);

  return { ...state, login, logout };
}

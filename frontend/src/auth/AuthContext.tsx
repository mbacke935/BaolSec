/**
 * Session de l'utilisateur (C3 4.6, C22, C23).
 *
 * Un seul contexte pour toute l'application : l'utilisateur est lu une fois après la connexion
 * (GET /auth/me). Les routes vérifient le rôle pour l'affichage ; l'API reste seule juge des
 * droits (ES-03) — masquer un écran n'est pas un contrôle de sécurité.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { auth } from '../api/endpoints';
import { clearTokens, errorMessage, getAccessToken, setSessionExpiredHandler, setTokens } from '../api/client';
import type { User, UserRole } from '../types/api';

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (login: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  expired: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(getAccessToken()));
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    setSessionExpiredHandler(() => { setUser(null); setExpired(true); });
    if (getAccessToken()) {
      auth.me().then(setUser).catch(() => { clearTokens(); setUser(null); }).finally(() => setLoading(false));
    }
    return () => setSessionExpiredHandler(null);
  }, []);

  const login = useCallback(async (loginName: string, password: string) => {
    const tokens = await auth.login(loginName, password);
    setTokens(tokens.access_token, tokens.refresh_token);
    try {
      const me = await auth.me();
      setUser(me);
      setExpired(false);
      return me;
    } catch (err) {
      clearTokens();
      throw new Error(errorMessage(err));
    }
  }, []);

  const logout = useCallback(async () => {
    await auth.logout();          // révocation côté serveur (C5) avant d'oublier les jetons
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout, expired }), [user, loading, login, logout, expired]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth doit être utilisé dans AuthProvider');
  return ctx;
}

export function homeFor(role: UserRole | undefined): string {
  return role === 'ADMIN' ? '/admin' : '/dashboard';
}

/** Route protégée : connexion obligatoire ; rôles facultatifs (sinon redirection vers l'accueil du rôle). */
export function RequireAuth({ roles, children }: { roles?: UserRole[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="boot">Ouverture de la session…</div>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (roles && !roles.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}

/**
 * Shell applicatif unifié BaolSec Nexus (IA de la maquette) : une seule
 * application, sidebar à 7 vues (+ Utilisateurs pour l'administrateur),
 * barre haute avec titre/sous-titre dynamiques et recherche globale.
 * Les gardes d'authentification protègent /app ; le RBAC reste côté serveur.
 */
import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import logo from '../assets/logo.jpg';

/* ── Recherche globale partagée avec les vues ──────────────────────────────── */
const SearchCtx = createContext<string>('');
export const useSearch = () => useContext(SearchCtx);

/* ── Table titres/sous-titres par route (repris de la maquette) ────────────── */
const META: Record<string, [string, string]> = {
  '/app': ['Vue générale', "Vue d'ensemble de votre environnement de sécurité"],
  '/app/events': ['Événements', 'Recherche et exploration des événements collectés'],
  '/app/alerts': ['Alertes', 'Qualification et suivi des alertes de sécurité'],
  '/app/incidents': ['Incidents', 'Investigation et suivi des incidents'],
  '/app/sources': ['Sources', 'État des équipements et sources de journaux'],
  '/app/rules': ['Détection', 'Configuration des règles de détection'],
  '/app/monitor': ['Supervision', 'État des composants de la plateforme'],
  '/app/users': ['Utilisateurs', 'Gestion des comptes et des rôles'],
};

const NAV: Array<{ icon: string; label: string; path: string }> = [
  { icon: '⌂', label: 'Vue générale', path: '/app' },
  { icon: '▤', label: 'Événements', path: '/app/events' },
  { icon: '♧', label: 'Alertes', path: '/app/alerts' },
  { icon: '◈', label: 'Incidents', path: '/app/incidents' },
  { icon: '⌘', label: 'Sources', path: '/app/sources' },
  { icon: '◎', label: 'Détection', path: '/app/rules' },
  { icon: '◷', label: 'Supervision', path: '/app/monitor' },
];

function titleFor(pathname: string): [string, string] {
  if (pathname.startsWith('/app/incidents/')) return ['Incident', "Détail et chronologie de l'incident"];
  return META[pathname] ?? META['/app'];
}

function Loading() {
  return <div style={{ padding: '2rem', color: 'var(--muted)', fontFamily: 'Inter' }}>Chargement…</div>;
}

export function AppShell() {
  const { user, loading, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  // La recherche se réinitialise à chaque changement de vue (comme la maquette).
  useEffect(() => { setQuery(''); }, [location.pathname]);

  const isAdmin = user?.role === 'ADMIN';
  const nav = useMemo(
    () => (isAdmin ? [...NAV, { icon: '⚙', label: 'Utilisateurs', path: '/app/users' }] : NAV),
    [isAdmin],
  );

  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;

  const [title, sub] = titleFor(location.pathname);
  const active = (path: string) =>
    path === '/app' ? location.pathname === '/app' : location.pathname.startsWith(path);

  return (
    <SearchCtx.Provider value={query}>
      <div className="app-shell">
        <aside className="side">
          <a className="brand" href="/" onClick={(e) => { e.preventDefault(); navigate('/'); }}>
            <img src={logo} alt="BaolSec" />
            <span>BaolSec</span>
          </a>
          <div className="side-label">ESPACE SOC</div>
          {nav.map((n) => (
            <button
              key={n.path}
              className={`navlink${active(n.path) ? ' active' : ''}`}
              data-icon={n.icon}
              onClick={() => navigate(n.path)}
            >
              <span className="lbl-txt">{n.icon}　{n.label}</span>
            </button>
          ))}
          <div className="user">
            <div className="uname">{user.email ?? user.username}</div>
            <div className="urole">{isAdmin ? 'Administrateur' : 'Analyste'}</div>
            <div className="ulinks">
              <button onClick={() => navigate('/')}>← Site</button>
              <button onClick={() => navigate('/login')}>Changer de rôle</button>
              <button onClick={logout}>Déconnexion</button>
            </div>
          </div>
        </aside>

        <main className="main">
          <div className="app-top">
            <div className="app-title">
              <h2>{title}</h2>
              <p>{sub}</p>
            </div>
            <div className="top-right">
              <input
                className="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="⌕  Rechercher dans la vue…"
              />
              <button className="pill" onClick={() => navigate('/')}>← Site</button>
            </div>
          </div>
          <Outlet />
        </main>
      </div>
    </SearchCtx.Provider>
  );
}

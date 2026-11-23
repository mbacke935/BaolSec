import { type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import '../styles/design-system.css';

const NAV = [
  { path: '/dashboard',  icon: '◈', label: 'Tableau de bord' },
  { path: '/incidents',  icon: '⚡', label: 'Incidents' },
  { path: '/alerts',     icon: '◉', label: 'Alertes' },
  { path: '/events',     icon: '▦',  label: 'Événements' },
  { path: '/search',     icon: '⌕', label: 'Recherche' },
  { path: '/coverage',   icon: '◎', label: 'Couverture' },
  { path: '/monitor',    icon: '♡',  label: 'Supervision' },
];

function initials(email?: string) {
  if (!email) return 'A';
  return email.slice(0, 2).toUpperCase();
}

export function AnalystLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
    <div className="bs-shell">
      <aside className="bs-sidebar">
        {/* Logo */}
        <div className="bs-logo">
          <img src="/assets/logo.jpg" alt="BaolSec" style={{ height: 26, width: 'auto', borderRadius: 4 }} />
          <div>
            <div className="bs-logo-name">Baol<span>Sec</span></div>
          </div>
          <span className="bs-logo-badge analyst">SOC</span>
        </div>

        {/* Navigation */}
        <span className="bs-nav-label">Analyse</span>

        {NAV.map(({ path, icon, label }) => {
          const active = location.pathname === path || (path !== '/dashboard' && location.pathname.startsWith(path));
          return (
            <Link key={path} to={path} className={`bs-nav-link${active ? ' active' : ''}`}>
              <span className="nav-icon">{icon}</span>
              {label}
            </Link>
          );
        })}

        {/* Footer */}
        <div className="bs-sidebar-footer">
          <div className="bs-user-chip">
            <div className="bs-user-avatar">{initials(user?.email)}</div>
            <div className="bs-user-info">
              <div className="bs-user-role">Analyste SOC</div>
              <div className="bs-user-email">{user?.email}</div>
            </div>
          </div>
          <button className="bs-logout-btn" onClick={logout}>
            <span>⇠</span> Déconnexion
          </button>
        </div>
      </aside>

      <main className="bs-main">{children}</main>
    </div>
  );
}

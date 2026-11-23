import { type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import '../styles/design-system.css';

const NAV = [
  { path: '/admin',   icon: '◈', label: 'Tableau de bord' },
  { path: '/sources', icon: '◉', label: 'Sources de données' },
  { path: '/rules',   icon: '⚡', label: 'Règles de détection' },
  { path: '/users',   icon: '◎', label: 'Utilisateurs' },
];

function initials(email?: string) {
  if (!email) return 'A';
  return email.slice(0, 2).toUpperCase();
}

export function AdminLayout({ children }: { children: ReactNode }) {
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
          <span className="bs-logo-badge admin">Admin</span>
        </div>

        {/* Navigation */}
        <span className="bs-nav-label">Administration</span>

        {NAV.map(({ path, icon, label }) => {
          // Pour /admin, active seulement si exact (pour éviter de matcher /admin + /sources etc.)
          const active = path === '/admin'
            ? location.pathname === '/admin'
            : location.pathname.startsWith(path);
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
              <div className="bs-user-role">Administrateur</div>
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

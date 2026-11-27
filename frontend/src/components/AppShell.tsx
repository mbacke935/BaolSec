/**
 * Coquille de l'application : barre latérale par rôle (matrice C2 §3), fil d'Ariane, session.
 * Analyste : traite alertes et incidents, consulte événements, couverture et référentiel.
 * Administrateur : gère utilisateurs, sources, règles, paramètres ; consulte audit et file de rejet ;
 * lit alertes, incidents et événements sans pouvoir les traiter.
 */
import { useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { alerts, incidents } from '../api/endpoints';
import { useAuth } from '../auth/AuthContext';
import { ROLE } from '../lib/format';
import {
  IconAudit, IconBell, IconDashboard, IconFlame, IconInbox, IconList, IconLogout, IconMenu, IconPulse,
  IconRadar, IconRule, IconSearch, IconServer, IconSettings, IconUsers,
} from './icons';
import { ActivityBar } from './ui';

interface NavItem { to: string; label: string; icon: ReactNode; count?: number }
interface NavGroup { title: string; items: NavItem[] }

const TITLES: Record<string, string> = {
  '/dashboard': 'Tableau de bord', '/alerts': 'Alertes', '/incidents': 'Incidents', '/events': 'Événements',
  '/search': 'Recherche avancée', '/coverage': 'Couverture des sources', '/monitor': 'Supervision',
  '/admin': "Vue d'ensemble", '/sources': 'Sources', '/rules': 'Règles de détection', '/users': 'Utilisateurs',
  '/settings': 'Paramètres', '/audit': "Journal d'audit", '/dlq': 'File de rejet',
};

function initials(name: string): string {
  const parts = name.replace(/@.*/, '').split(/[.\s_-]+/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2)).toUpperCase();
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const isAdmin = user?.role === 'ADMIN';

  const newAlerts = useQuery({
    queryKey: ['nav', 'alerts-new'], queryFn: () => alerts.list({ status: 'nouvelle', limit: 200 }),
    refetchInterval: 30_000, enabled: !!user,
  });
  const activeIncidents = useQuery({
    queryKey: ['nav', 'incidents-active'], queryFn: () => incidents.list({ active_only: true, limit: 200 }),
    refetchInterval: 30_000, enabled: !!user,
  });

  const analyse: NavItem[] = [
    { to: '/alerts', label: 'Alertes', icon: <IconBell />, count: newAlerts.data?.length },
    { to: '/incidents', label: 'Incidents', icon: <IconFlame />, count: activeIncidents.data?.length },
    { to: '/events', label: 'Événements', icon: <IconList /> },
    { to: '/search', label: 'Recherche avancée', icon: <IconSearch /> },
  ];
  const surveillance: NavItem[] = [
    { to: '/coverage', label: 'Couverture des sources', icon: <IconRadar /> },
    { to: '/monitor', label: 'Supervision', icon: <IconPulse /> },
  ];
  const groups: NavGroup[] = isAdmin
    ? [
        { title: 'Administration', items: [
          { to: '/admin', label: "Vue d'ensemble", icon: <IconDashboard /> },
          { to: '/sources', label: 'Sources', icon: <IconServer /> },
          { to: '/rules', label: 'Règles de détection', icon: <IconRule /> },
          { to: '/users', label: 'Utilisateurs', icon: <IconUsers /> },
          { to: '/settings', label: 'Paramètres', icon: <IconSettings /> },
        ] },
        { title: 'Traçabilité', items: [
          { to: '/audit', label: "Journal d'audit", icon: <IconAudit /> },
          { to: '/dlq', label: 'File de rejet', icon: <IconInbox /> },
        ] },
        { title: 'Consultation', items: [...analyse.map((i) => ({ ...i, count: undefined })), ...surveillance] },
      ]
    : [
        { title: 'Analyse', items: [{ to: '/dashboard', label: 'Tableau de bord', icon: <IconDashboard /> }, ...analyse] },
        { title: 'Surveillance', items: surveillance },
        { title: 'Référentiel', items: [
          { to: '/sources', label: 'Sources', icon: <IconServer /> },
          { to: '/rules', label: 'Règles de détection', icon: <IconRule /> },
        ] },
      ];

  const section = '/' + (location.pathname.split('/')[1] ?? '');
  const title = TITLES[section] ?? 'BaolSec';
  const sub = location.pathname.startsWith('/incidents/') ? 'Détail' : null;

  async function onLogout() {
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <div className={`shell ${open ? 'nav-open' : ''}`}>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <aside className="sidebar" aria-label="Navigation principale">
        <div className="sidebar__brand">
          <img className="brand-mark" src="/assets/logo-mark.png" alt="" />
          <div className="brand-name">Baol<span>Sec</span></div>
          <span className="brand-role">{isAdmin ? 'Admin' : 'SOC'}</span>
        </div>
        <nav className="sidebar__nav" onClick={() => setOpen(false)}>
          {groups.map((g) => (
            <div key={g.title}>
              <div className="nav-section">{g.title}</div>
              {g.items.map((item) => (
                <NavLink key={item.to} to={item.to} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                  {item.icon}<span>{item.label}</span>
                  {item.count ? <span key={item.count} className="nav-count" aria-label={`${item.count} à traiter`}>{item.count > 99 ? '99+' : item.count}</span> : null}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar__user">
          <div className="avatar" aria-hidden>{initials(user?.username ?? user?.email ?? '?')}</div>
          <div className="who">
            <strong title={user?.email ?? ''}>{user?.username}</strong>
            <span>{user ? ROLE[user.role] : ''}</span>
          </div>
          <button className="btn ghost icon" style={{ marginLeft: 'auto' }} onClick={onLogout} title="Se déconnecter" aria-label="Se déconnecter"><IconLogout /></button>
        </div>
      </aside>
      <div className="main">
        <ActivityBar />
        <div className="topbar">
          <button className="btn ghost icon menu-toggle" onClick={() => setOpen(true)} aria-label="Ouvrir le menu"><IconMenu /></button>
          <div className="crumbs">{isAdmin ? 'Administration' : 'Analyse'} · <b>{title}</b>{sub && <> · {sub}</>}</div>
          <div className="spacer" />
          <span className="small faint nowrap session">Session : {user?.email ?? user?.username}</span>
        </div>
        <main className="content"><div key={location.pathname} className="page-enter">{children}</div></main>
      </div>
    </div>
  );
}

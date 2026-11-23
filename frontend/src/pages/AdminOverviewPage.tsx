/**
 * Tableau de bord administrateur — vue d'ensemble et raccourcis rapides.
 * Donne accès direct aux actions courantes : ajouter une source, créer une règle, etc.
 */
import type { CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { sources as sourcesApi, rules as rulesApi, users as usersApi, toList } from '../api/resources';
import type { Source, Rule, User } from '../types/api';
import '../styles/design-system.css';

interface QuickAction {
  label: string;
  desc: string;
  icon: string;
  path: string;
  color: string;
  primary?: boolean;
}

const ACTIONS: QuickAction[] = [
  {
    label: 'Ajouter une source',
    desc: 'Connecter une nouvelle source de données au SIEM',
    icon: '◉',
    path: '/sources',
    color: 'var(--accent)',
    primary: true,
  },
  {
    label: 'Créer une règle',
    desc: 'Définir une règle de détection ou de corrélation',
    icon: '⚡',
    path: '/rules',
    color: 'var(--warn)',
  },
  {
    label: 'Gérer les utilisateurs',
    desc: "Ajouter ou désactiver des comptes d'accès",
    icon: '◎',
    path: '/users',
    color: 'var(--accent3)',
  },
];

export function AdminOverviewPage() {
  const navigate = useNavigate();

  const { data: rawSources, isLoading: loadSrc } = useQuery({
    queryKey: ['sources'],
    queryFn: () => sourcesApi.list(),
  });
  const { data: rawRules, isLoading: loadRules } = useQuery({
    queryKey: ['rules'],
    queryFn: () => rulesApi.list(),
  });
  const { data: rawUsers, isLoading: loadUsers } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list(),
  });

  const sourceList = toList<Source>(rawSources);
  const ruleList   = toList<Rule>(rawRules);
  const userList   = toList<User>(rawUsers);

  const activeSources = sourceList.filter((s) => s.active).length;
  const activeRules   = ruleList.filter((r) => r.enabled).length;
  const activeUsers   = userList.filter((u) => u.is_active).length;

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title">Administration <span>BaolSec</span></h1>
          <p className="bs-page-sub">Gestion des sources, règles et accès utilisateurs</p>
        </div>
      </div>

      {/* KPIs */}
      <div className="bs-kpi-grid">
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent)' } as CSSProperties}>
          <div className="bs-kpi-label">Sources actives</div>
          <div className="bs-kpi-value bs-glow-accent">{loadSrc ? '…' : activeSources}</div>
          <div className="bs-kpi-sub">sur {sourceList.length} sources configurées</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--warn)' } as CSSProperties}>
          <div className="bs-kpi-label">Règles actives</div>
          <div className="bs-kpi-value">{loadRules ? '…' : activeRules}</div>
          <div className="bs-kpi-sub">sur {ruleList.length} règles configurées</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent3)' } as CSSProperties}>
          <div className="bs-kpi-label">Utilisateurs actifs</div>
          <div className="bs-kpi-value">{loadUsers ? '…' : activeUsers}</div>
          <div className="bs-kpi-sub">sur {userList.length} comptes enregistrés</div>
        </div>
      </div>

      {/* Actions rapides */}
      <div className="bs-card bs-mb-16">
        <div className="bs-section-header bs-mb-16">
          <span className="bs-section-title">Actions rapides</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          {ACTIONS.map((a) => (
            <button
              key={a.path}
              className={`bs-btn ${a.primary ? 'bs-btn-primary' : 'bs-btn-secondary'}`}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                gap: 6, padding: '14px 16px', height: 'auto',
                borderColor: a.primary ? undefined : `${a.color}44`,
              }}
              onClick={() => navigate(a.path)}
            >
              <span style={{ fontSize: 20, color: a.primary ? undefined : a.color }}>{a.icon}</span>
              <span style={{ fontWeight: 700, fontSize: 13 }}>{a.label}</span>
              <span style={{ fontSize: 11, fontWeight: 400, opacity: 0.75, whiteSpace: 'normal', textAlign: 'left' }}>
                {a.desc}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Résumé état du système */}
      <div className="bs-card">
        <div className="bs-section-header bs-mb-16">
          <span className="bs-section-title">État du système</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[
            {
              label: 'Sources de données',
              ok: activeSources > 0,
              msg: loadSrc ? 'Chargement…' : activeSources > 0
                ? `${activeSources} source(s) active(s)` : 'Aucune source configurée',
              action: () => navigate('/sources'),
              actionLabel: activeSources === 0 ? '+ Ajouter une source' : 'Gérer →',
            },
            {
              label: 'Règles de détection',
              ok: activeRules > 0,
              msg: loadRules ? 'Chargement…' : activeRules > 0
                ? `${activeRules} règle(s) active(s)` : 'Aucune règle activée',
              action: () => navigate('/rules'),
              actionLabel: activeRules === 0 ? '+ Créer une règle' : 'Gérer →',
            },
            {
              label: 'Accès utilisateurs',
              ok: activeUsers > 0,
              msg: loadUsers ? 'Chargement…' : activeUsers > 0
                ? `${activeUsers} compte(s) actif(s)` : 'Aucun utilisateur actif',
              action: () => navigate('/users'),
              actionLabel: 'Gérer →',
            },
          ].map(({ label, ok, msg, action, actionLabel }) => (
            <div
              key={label}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 14px',
                background: ok ? 'rgba(16,185,129,0.06)' : 'rgba(255,68,102,0.06)',
                borderRadius: 'var(--radius)',
                border: `1px solid ${ok ? 'rgba(16,185,129,0.15)' : 'rgba(255,68,102,0.15)'}`,
              }}
            >
              <span style={{
                width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                background: ok ? 'var(--success)' : 'var(--danger)',
                boxShadow: `0 0 5px ${ok ? 'var(--success)' : 'var(--danger)'}`,
              }} />
              <span style={{ flex: 1, fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>{label}</span>
              <span style={{ fontSize: 12, color: 'var(--fg3)' }}>{msg}</span>
              <button
                className="bs-btn bs-btn-secondary bs-btn-xs"
                onClick={action}
                style={ok ? {} : { color: 'var(--accent)', borderColor: 'rgba(0,212,170,0.3)' }}
              >
                {actionLabel}
              </button>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

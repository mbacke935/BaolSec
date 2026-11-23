/**
 * Vue générale (dashboard) — données réelles de l'API :
 * KPI (événements, alertes, incidents, sources), répartition par sévérité,
 * et table des alertes récentes.
 */
import type { CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { incidents, alerts, coverage, toList } from '../api/analyst';
import type { Incident, Alert, CoverageState } from '../api/analyst';
import '../styles/design-system.css';

function fmtCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)} k`;
  return n.toString();
}

const SEV_BARS = [
  { key: 'CRITIQUE', label: 'Critique', color: 'var(--danger)' },
  { key: 'ELEVE',    label: 'Élevée',   color: 'var(--warn)' },
  { key: 'MOYEN',    label: 'Moyenne',  color: 'var(--accent2)' },
  { key: 'FAIBLE',   label: 'Faible',   color: 'var(--accent)' },
] as const;

const ACTIVE_STATES = ['OUVERT', 'EN_COURS'];

function sevClass(s: string): string {
  if (s === 'CRITIQUE') return 'critique';
  if (s === 'ELEVE') return 'eleve';
  if (s === 'MOYEN') return 'warn';
  return 'info';
}

export function OverviewPage() {
  const navigate = useNavigate();
  const incQ   = useQuery({ queryKey: ['incidents'], queryFn: () => incidents.list({ limit: 200 }) });
  const alertQ = useQuery({ queryKey: ['alerts'],    queryFn: () => alerts.list({ limit: 200 }) });
  const covQ   = useQuery({ queryKey: ['coverage'],  queryFn: () => coverage.list(), refetchInterval: 30_000 });

  const incList  = toList<Incident>(incQ.data);
  const alertList= toList<Alert>(alertQ.data);
  const covList  = toList<CoverageState>(covQ.data);

  const activeInc   = incList.filter((i) => ACTIVE_STATES.includes(i.state)).length;
  const totalEvents = covList.reduce((s, c) => s + (c.received_count ?? 0), 0);
  const sourcesOk   = covList.filter((c) => c.state === 'ACTIVE').length;
  const srcName     = new Map(covList.map((c) => [c.source_id, c.source_name]));

  // Répartition des alertes par sévérité
  const counts: Record<string, number> = { CRITIQUE: 0, ELEVE: 0, MOYEN: 0, FAIBLE: 0 };
  for (const a of alertList) {
    const k = a.severity.toUpperCase();
    if (k in counts) counts[k]++;
    else counts.FAIBLE++;
  }
  const maxSev = Math.max(1, ...Object.values(counts));

  const recent = alertList.slice(0, 6);

  const isLoading = incQ.isLoading || alertQ.isLoading || covQ.isLoading;

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title">Tableau de <span>bord</span></h1>
          <p className="bs-page-sub">Vue d'ensemble de la posture de sécurité</p>
        </div>
        {isLoading && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--fg4)' }}>
            <span className="bs-spinner" style={{ width: 12, height: 12 }} /> Actualisation…
          </span>
        )}
      </div>

      {/* KPIs */}
      <div className="bs-kpi-grid">
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--accent)' } as CSSProperties}>
          <div className="bs-kpi-label">Événements analysés</div>
          <div className="bs-kpi-value bs-glow-accent">
            {covQ.isLoading ? '…' : fmtCompact(totalEvents)}
          </div>
          <div className="bs-kpi-sub">Cumul reçu sur toutes les sources</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': counts.CRITIQUE > 0 ? 'var(--danger)' : 'var(--warn)' } as CSSProperties}>
          <div className="bs-kpi-label">Alertes</div>
          <div className={`bs-kpi-value ${counts.CRITIQUE > 0 ? 'bs-glow-danger' : ''}`}>
            {alertQ.isLoading ? '…' : alertList.length}
          </div>
          <div className="bs-kpi-sub">{counts.CRITIQUE} critique(s)</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': activeInc > 0 ? 'var(--danger)' : 'var(--success)' } as CSSProperties}>
          <div className="bs-kpi-label">Incidents actifs</div>
          <div className={`bs-kpi-value ${activeInc > 0 ? 'bs-glow-danger' : ''}`}>
            {incQ.isLoading ? '…' : activeInc}
          </div>
          <div className="bs-kpi-sub">sur {incList.length} au total</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--success)' } as CSSProperties}>
          <div className="bs-kpi-label">Sources actives</div>
          <div className="bs-kpi-value bs-glow-accent">
            {covQ.isLoading ? '…' : `${sourcesOk} / ${covList.length}`}
          </div>
          <div className="bs-kpi-sub">
            {covList.length ? Math.round((sourcesOk / covList.length) * 100) : 0} % opérationnelles
          </div>
        </div>
      </div>

      {/* Grille : activité + répartition */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16, marginBottom: 16 }}>

        {/* Activité de sécurité */}
        <div className="bs-card">
          <div className="bs-section-header bs-mb-16">
            <span className="bs-section-title">Activité de sécurité</span>
            <span style={{ fontSize: 11, color: 'var(--fg4)' }}>Tendance illustrative</span>
          </div>
          <svg
            viewBox="0 0 600 160"
            style={{ width: '100%', height: 'auto', display: 'block' }}
            preserveAspectRatio="none"
          >
            <defs>
              <linearGradient id="grd-ev" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor="var(--accent)" stopOpacity=".25" />
                <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
              </linearGradient>
              <linearGradient id="grd-al" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0" stopColor="var(--danger)" stopOpacity=".2" />
                <stop offset="1" stopColor="var(--danger)" stopOpacity="0" />
              </linearGradient>
            </defs>
            {/* Courbe événements */}
            <path
              d="M0 115 C35 100 40 115 70 85 S120 105 150 75 S190 92 220 60 S260 90 295 62 S330 75 365 35 S410 70 445 45 S480 60 510 18 S560 52 600 5 L600 160 L0 160Z"
              fill="url(#grd-ev)"
            />
            <path
              d="M0 115 C35 100 40 115 70 85 S120 105 150 75 S190 92 220 60 S260 90 295 62 S330 75 365 35 S410 70 445 45 S480 60 510 18 S560 52 600 5"
              fill="none" stroke="var(--accent)" strokeWidth="2"
            />
            {/* Courbe alertes (plus basse) */}
            <path
              d="M0 140 C35 135 70 138 100 125 S140 130 170 118 S210 128 240 115 S280 122 310 108 S360 118 400 102 S450 112 490 95 S560 105 600 88 L600 160 L0 160Z"
              fill="url(#grd-al)"
            />
            <path
              d="M0 140 C35 135 70 138 100 125 S140 130 170 118 S210 128 240 115 S280 122 310 108 S360 118 400 102 S450 112 490 95 S560 105 600 88"
              fill="none" stroke="var(--danger)" strokeWidth="1.5" strokeDasharray="4 3"
            />
          </svg>
          <div style={{ display: 'flex', gap: 16, marginTop: 10 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--fg3)' }}>
              <span style={{ width: 12, height: 2, background: 'var(--accent)', display: 'inline-block', borderRadius: 1 }} />
              Événements
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--fg3)' }}>
              <span style={{ width: 12, height: 2, background: 'var(--danger)', display: 'inline-block', borderRadius: 1, opacity: 0.7 }} />
              Alertes
            </span>
          </div>
        </div>

        {/* Répartition des alertes */}
        <div className="bs-card">
          <div className="bs-section-header bs-mb-16">
            <span className="bs-section-title">Répartition par sévérité</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {SEV_BARS.map((s) => {
              const pct = Math.round((counts[s.key] / maxSev) * 100);
              return (
                <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ width: 70, fontSize: 12, color: 'var(--fg3)', flexShrink: 0 }}>{s.label}</span>
                  <div style={{ flex: 1, background: 'rgba(255,255,255,0.05)', borderRadius: 4, overflow: 'hidden', height: 8 }}>
                    <div style={{
                      height: '100%', borderRadius: 4,
                      background: s.color,
                      width: `${pct}%`,
                      transition: 'width 0.5s ease',
                      boxShadow: `0 0 6px ${s.color}66`,
                    }} />
                  </div>
                  <span className="bs-mono" style={{ fontSize: 12, fontWeight: 600, color: 'var(--fg2)', minWidth: 24, textAlign: 'right' }}>
                    {counts[s.key]}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Résumé couverture */}
          <div style={{
            marginTop: 20, padding: '10px 12px', borderRadius: 'var(--radius)',
            background: sourcesOk === covList.length && covList.length > 0
              ? 'rgba(16,185,129,0.08)' : 'rgba(245,158,11,0.08)',
            border: `1px solid ${sourcesOk === covList.length && covList.length > 0
              ? 'rgba(16,185,129,0.2)' : 'rgba(245,158,11,0.2)'}`,
            fontSize: 12, color: 'var(--fg2)',
          }}>
            {covQ.isLoading
              ? 'Chargement de la couverture…'
              : `${sourcesOk} source(s) active(s) sur ${covList.length}`}
          </div>
        </div>
      </div>

      {/* Alertes récentes */}
      <div className="bs-card" style={{ padding: 0 }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--fg)' }}>Alertes récentes</span>
          <button
            className="bs-btn bs-btn-secondary bs-btn-xs"
            onClick={() => navigate('/alerts')}
          >
            Voir toutes →
          </button>
        </div>

        {alertQ.isLoading ? (
          <div className="bs-loading" style={{ padding: 20 }}>
            <div className="bs-spinner" /> Chargement des alertes…
          </div>
        ) : (
          <div className="bs-table-wrap" style={{ border: 'none' }}>
            <table className="bs-table">
              <thead>
                <tr>
                  <th>Règle</th>
                  <th>Titre</th>
                  <th>Source</th>
                  <th>Sévérité</th>
                  <th>Déclenchée</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <span className="bs-code" style={{ fontSize: 11 }}>
                        {a.rule_id ? a.rule_id.slice(0, 8) : '—'}
                      </span>
                    </td>
                    <td style={{ color: 'var(--fg)', fontWeight: 500, maxWidth: 260 }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
                        {a.title}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--fg3)' }}>
                      {a.source_id ? (srcName.get(a.source_id) ?? a.source_id.slice(0, 8)) : '—'}
                    </td>
                    <td>
                      <span className={`bs-badge ${sevClass(a.severity)}`}>{a.severity}</span>
                    </td>
                    <td className="bs-mono" style={{ fontSize: 11, color: 'var(--fg3)' }}>
                      {new Date(a.fired_at).toLocaleString('fr-FR', {
                        day: '2-digit', month: '2-digit',
                        hour: '2-digit', minute: '2-digit',
                      })}
                    </td>
                  </tr>
                ))}
                {recent.length === 0 && (
                  <tr>
                    <td colSpan={5}>
                      <div className="bs-empty">
                        <div className="bs-empty-icon">◉</div>
                        <div className="bs-empty-text">Aucune alerte récente</div>
                        <div className="bs-empty-sub">Le système de détection n'a pas produit d'alerte récemment</div>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

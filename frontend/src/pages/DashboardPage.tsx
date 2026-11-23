import type { CSSProperties } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { alerts, coverage, incidents, toList } from '../api/analyst';
import type { Alert, CoverageState, Incident } from '../api/analyst';
import '../styles/design-system.css';

function severityClass(s: string) { return s.toLowerCase(); }
function stateClass(s: string)    { return s.toLowerCase(); }
function coverageClass(s: string) {
  if (s === 'ACTIVE') return 'active';
  if (s === 'SILENCIEUSE' || s === 'FLUX_INCOMPLET') return 'warn';
  return 'neutral';
}

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'à l\'instant';
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h`;
  return `${Math.floor(h / 24)} j`;
}

function stateLabel(s: string) {
  const labels: Record<string, string> = {
    ACTIVE: 'Active', SILENCIEUSE: 'Silencieuse',
    FLUX_INCOMPLET: 'Incomplet', DESACTIVEE: 'Désactivée',
  };
  return labels[s] ?? s;
}

export function DashboardPage() {
  const { data: incRaw, isLoading: loadInc } = useQuery({
    queryKey: ['incidents'],
    queryFn: () => incidents.list({ limit: 200 }),
  });
  const { data: alertRaw, isLoading: loadAlert } = useQuery({
    queryKey: ['alerts-recent'],
    queryFn: () => alerts.list({ limit: 20 }),
  });
  const { data: coverageRaw, isLoading: loadCov } = useQuery({
    queryKey: ['coverage'],
    queryFn: () => coverage.list(),
  });

  const incidentList = toList<Incident>(incRaw);
  const alertList    = toList<Alert>(alertRaw);
  const coverageList = toList<CoverageState>(coverageRaw);

  const openInc    = incidentList.filter((i) => i.state === 'OUVERT' || i.state === 'EN_COURS');
  const criticalInc = openInc.filter((i) => i.severity === 'CRITIQUE' || i.severity === 'ELEVE');
  const activeSrc  = coverageList.filter((c) => c.state === 'ACTIVE').length;
  const warnSrc    = coverageList.filter((c) => c.state === 'SILENCIEUSE' || c.state === 'FLUX_INCOMPLET').length;

  return (
    <>
      <div className="bs-page-header">
        <div>
          <h1 className="bs-page-title">Tableau de <span>bord</span></h1>
          <p className="bs-page-sub">Vue opérationnelle en temps réel — SOC BaolSec</p>
        </div>
        <Link to="/incidents" className="bs-btn bs-btn-secondary bs-btn-sm">
          Tous les incidents →
        </Link>
      </div>

      {/* KPIs */}
      <div className="bs-kpi-grid">
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--danger)' } as CSSProperties}>
          <div className="bs-kpi-label">Incidents ouverts</div>
          <div className={`bs-kpi-value ${openInc.length > 0 ? 'bs-glow-danger' : ''}`}>
            {loadInc ? '…' : openInc.length}
          </div>
          <div className="bs-kpi-sub">En cours de traitement</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': '#ff6680' } as CSSProperties}>
          <div className="bs-kpi-label">Critique / Élevé</div>
          <div className={`bs-kpi-value ${criticalInc.length > 0 ? 'bs-glow-danger' : ''}`}>
            {loadInc ? '…' : criticalInc.length}
          </div>
          <div className="bs-kpi-sub">Priorité immédiate</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--warn)' } as CSSProperties}>
          <div className="bs-kpi-label">Alertes récentes</div>
          <div className="bs-kpi-value">{loadAlert ? '…' : alertList.length}</div>
          <div className="bs-kpi-sub">20 dernières alertes</div>
        </div>
        <div className="bs-kpi" style={{ '--kpi-color': 'var(--success)' } as CSSProperties}>
          <div className="bs-kpi-label">Sources actives</div>
          <div className={`bs-kpi-value ${warnSrc > 0 ? 'bs-glow-warn' : 'bs-glow-accent'}`}>
            {loadCov ? '…' : activeSrc}
          </div>
          <div className="bs-kpi-sub">
            {warnSrc > 0 ? `${warnSrc} en anomalie` : 'Couverture nominale'}
          </div>
        </div>
      </div>

      <div className="bs-grid-2">
        {/* Incidents ouverts */}
        <div className="bs-card">
          <div className="bs-section-header">
            <span className="bs-section-title">Incidents actifs</span>
            {!loadInc && <span className="bs-section-count">{openInc.length}</span>}
          </div>

          {loadInc ? (
            <div className="bs-loading"><div className="bs-spinner" /> Chargement…</div>
          ) : openInc.length === 0 ? (
            <div className="bs-empty">
              <div className="bs-empty-icon">✓</div>
              <div className="bs-empty-text">Aucun incident ouvert</div>
              <div className="bs-empty-sub">Situation nominale</div>
            </div>
          ) : (
            <div className="bs-list">
              {openInc.slice(0, 10).map((inc) => (
                <Link key={inc.id} to={`/incidents/${inc.id}`} className="bs-list-item">
                  <span className={`bs-dot ${severityClass(inc.severity)}`} />
                  <span className="bs-list-item-title">{inc.title}</span>
                  <span className={`bs-badge ${stateClass(inc.state)}`}>{inc.state.replace('_', ' ')}</span>
                  <span className="bs-list-item-meta">{relTime(inc.opened_at)}</span>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Couverture sources */}
        <div className="bs-card">
          <div className="bs-section-header">
            <span className="bs-section-title">Couverture sources</span>
            <Link to="/coverage" className="bs-text-sm bs-text-accent">Détails →</Link>
          </div>

          {loadCov ? (
            <div className="bs-loading"><div className="bs-spinner" /> Chargement…</div>
          ) : coverageList.length === 0 ? (
            <div className="bs-empty">
              <div className="bs-empty-icon">◎</div>
              <div className="bs-empty-text">Aucune source configurée</div>
            </div>
          ) : (
            <div className="bs-list">
              {coverageList.map((c) => (
                <div key={c.source_id} className="bs-list-item" style={{ cursor: 'default' }}>
                  <span className={`bs-dot ${coverageClass(c.state)}`} />
                  <span className="bs-list-item-title">{c.source_name}</span>
                  <span className={`bs-badge ${coverageClass(c.state)}`}>{stateLabel(c.state)}</span>
                  <span className="bs-list-item-meta bs-mono" style={{ fontSize: 10 }}>
                    {c.last_received_at
                      ? new Date(c.last_received_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
                      : '—'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Alertes récentes — pleine largeur */}
        <div className="bs-card" style={{ gridColumn: '1 / -1' }}>
          <div className="bs-section-header">
            <span className="bs-section-title">Alertes récentes</span>
            <Link to="/alerts" className="bs-text-sm bs-text-accent">Toutes les alertes →</Link>
          </div>

          {loadAlert ? (
            <div className="bs-loading"><div className="bs-spinner" /> Chargement…</div>
          ) : alertList.length === 0 ? (
            <div className="bs-empty">
              <div className="bs-empty-icon">◉</div>
              <div className="bs-empty-text">Aucune alerte récente</div>
            </div>
          ) : (
            <div className="bs-table-wrap">
              <table className="bs-table">
                <thead>
                  <tr>
                    <th>Sévérité</th>
                    <th>Titre de l'alerte</th>
                    <th>Règle</th>
                    <th>Source</th>
                    <th>Horodatage</th>
                  </tr>
                </thead>
                <tbody>
                  {alertList.slice(0, 10).map((a: Alert) => (
                    <tr key={a.id}>
                      <td><span className={`bs-badge ${severityClass(a.severity)}`}>{a.severity}</span></td>
                      <td style={{ color: 'var(--fg)', maxWidth: 300 }}>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
                          {a.title}
                        </span>
                      </td>
                      <td>
                        <span className="bs-code">{a.rule_id?.slice(0, 8) ?? '—'}</span>
                      </td>
                      <td>
                        <span className="bs-code">{a.source_id?.slice(0, 8) ?? '—'}</span>
                      </td>
                      <td className="bs-mono" style={{ fontSize: 11, color: 'var(--fg3)', whiteSpace: 'nowrap' }}>
                        {new Date(a.fired_at).toLocaleString('fr-FR', {
                          day: '2-digit', month: '2-digit',
                          hour: '2-digit', minute: '2-digit',
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

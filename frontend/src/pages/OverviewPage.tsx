/**
 * Vue générale (dashboard) — mise en page de la maquette, données réelles de l'API :
 * KPI (événements, alertes, incidents, sources), répartition des alertes par
 * sévérité, et table des alertes récentes. La courbe d'activité est illustrative.
 */
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { incidents, alerts, coverage } from '../api/analyst';
import { sevBadge, isActiveIncident, fmtCompact, fmtInt } from '../lib/ui';

const SEV_BARS = [
  { key: 'CRITIQUE', label: 'Critique', color: '#f05c68' },
  { key: 'ELEVE', label: 'Élevée', color: undefined }, // vert par défaut
  { key: 'MOYEN', label: 'Moyenne', color: '#eab45c' },
  { key: 'FAIBLE', label: 'Faible', color: '#48a5ed' },
] as const;

export function OverviewPage() {
  const navigate = useNavigate();
  const incQ = useQuery({ queryKey: ['incidents'], queryFn: () => incidents.list({ limit: 200 }) });
  const alertQ = useQuery({ queryKey: ['alerts'], queryFn: () => alerts.list({ limit: 200 }) });
  const covQ = useQuery({ queryKey: ['coverage'], queryFn: () => coverage.list() });

  const incList = incQ.data ?? [];
  const alertList = alertQ.data ?? [];
  const covList = covQ.data ?? [];

  const activeInc = incList.filter((i) => isActiveIncident(i.state)).length;
  const totalEvents = covList.reduce((s, c) => s + (c.received_count ?? 0), 0);
  const sourcesOk = covList.filter((c) => c.state === 'ACTIVE').length;
  const srcName = new Map(covList.map((c) => [c.source_id, c.source_name]));

  // Répartition des alertes par sévérité (FAIBLE regroupe INFO).
  const counts: Record<string, number> = { CRITIQUE: 0, ELEVE: 0, MOYEN: 0, FAIBLE: 0 };
  for (const a of alertList) {
    if (a.severity === 'CRITIQUE') counts.CRITIQUE++;
    else if (a.severity === 'ELEVE') counts.ELEVE++;
    else if (a.severity === 'MOYEN') counts.MOYEN++;
    else counts.FAIBLE++;
  }
  const maxSev = Math.max(1, ...Object.values(counts));

  const recent = alertList.slice(0, 6);

  return (
    <div>
      <div className="kpis">
        <div className="kpi">
          <small>Événements analysés</small>
          <strong>{covQ.isLoading ? '…' : fmtCompact(totalEvents)}</strong>
          <span className="up">Cumul reçu sur les sources</span>
        </div>
        <div className="kpi">
          <small>Alertes ouvertes</small>
          <strong>{alertQ.isLoading ? '…' : fmtInt(alertList.length)}</strong>
          <span className="up">{counts.CRITIQUE} critique(s)</span>
        </div>
        <div className="kpi">
          <small>Incidents actifs</small>
          <strong>{incQ.isLoading ? '…' : fmtInt(activeInc)}</strong>
          <span className="up">sur {incList.length} au total</span>
        </div>
        <div className="kpi">
          <small>Sources connectées</small>
          <strong>{covQ.isLoading ? '…' : `${sourcesOk} / ${covList.length}`}</strong>
          <span className="up">{covList.length ? Math.round((sourcesOk / covList.length) * 100) : 0} % actives</span>
        </div>
      </div>

      <div className="dash-grid">
        <div className="panel">
          <h3>Activité de sécurité</h3>
          <div className="chart">
            <svg preserveAspectRatio="none" viewBox="0 0 600 200">
              <defs>
                <linearGradient id="fill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0" stopColor="#36d69a" stopOpacity=".25" />
                  <stop offset="1" stopColor="#36d69a" stopOpacity="0" />
                </linearGradient>
              </defs>
              <path d="M0 145 C35 130 40 145 70 115 S120 135 150 105 S190 122 220 90 S260 120 295 92 S330 105 365 65 S410 100 445 75 S480 90 510 48 S560 82 600 35 L600 200 L0 200Z" fill="url(#fill)" />
              <path d="M0 145 C35 130 40 145 70 115 S120 135 150 105 S190 122 220 90 S260 120 295 92 S330 105 365 65 S410 100 445 75 S480 90 510 48 S560 82 600 35" fill="none" stroke="#36d69a" strokeWidth="3" />
            </svg>
          </div>
          <div className="legend">
            <span><i />Événements</span>
            <span><i className="blue" />Alertes</span>
            <span style={{ marginLeft: 'auto' }}>Tendance illustrative</span>
          </div>
        </div>

        <div className="panel">
          <h3>Répartition des alertes</h3>
          {SEV_BARS.map((s) => (
            <div className="threat" key={s.key}>
              <span>{s.label}</span>
              <div className="bar">
                <span style={{ width: `${(counts[s.key] / maxSev) * 100}%`, ...(s.color ? { background: s.color } : {}) }} />
              </div>
              <b>{counts[s.key]}</b>
            </div>
          ))}
          <div className="health" style={{ marginTop: 22 }}>
            <i />
            {covQ.isLoading ? 'Chargement de la couverture…' : `${sourcesOk} source(s) active(s) sur ${covList.length}`}
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 14 }}>
        <h3>
          Alertes récentes
          <span
            style={{ float: 'right', color: 'var(--green2)', fontSize: 11, fontWeight: 500, cursor: 'pointer' }}
            onClick={() => navigate('/app/alerts')}
          >
            Voir toutes les alertes →
          </span>
        </h3>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>RÈGLE</th><th>DESCRIPTION</th><th>SOURCE</th><th>GRAVITÉ</th><th>STATUT</th></tr>
            </thead>
            <tbody>
              {recent.map((a) => {
                const b = sevBadge(a.severity);
                return (
                  <tr key={a.id}>
                    <td>{a.rule_id ? a.rule_id.slice(0, 8) : '—'}</td>
                    <td>{a.title}</td>
                    <td>{a.source_id ? (srcName.get(a.source_id) ?? a.source_id.slice(0, 8)) : '—'}</td>
                    <td><span className={b.cls}>{b.label}</span></td>
                    <td>{a.incident_id ? 'Corrélée' : 'Nouvelle'}</td>
                  </tr>
                );
              })}
              {!alertQ.isLoading && recent.length === 0 && (
                <tr><td colSpan={5} className="empty-note">Aucune alerte pour le moment.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

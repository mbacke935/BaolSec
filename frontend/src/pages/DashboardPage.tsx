/**
 * Tableau de bord d'analyse (C23).
 * Compteurs : incidents ouverts, alertes récentes, couverture sources.
 */
import { useQuery } from '@tanstack/react-query';
import { alerts, coverage, incidents } from '../api/analyst';
import type { CoverageState, Incident } from '../api/analyst';

const SEVERITY_DOT: Record<string, string> = {
  CRITIQUE: '#ef4444',
  ELEVE:    '#f97316',
  MOYEN:    '#eab308',
  FAIBLE:   '#22c55e',
  INFO:     '#3b82f6',
};

const COVERAGE_DOT: Record<string, string> = {
  ACTIVE:         '#22c55e',
  SILENCIEUSE:    '#eab308',
  FLUX_INCOMPLET: '#f97316',
  DESACTIVEE:     '#6b7280',
  INCONNUE:       '#6b7280',
};

function StatCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div style={{ background: '#1e293b', borderRadius: '0.5rem', padding: '1.25rem', flex: '1', minWidth: '160px' }}>
      <p style={{ color: '#64748b', fontSize: '0.8rem', margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</p>
      <p style={{ color: color || '#e2e8f0', fontSize: '2rem', margin: '0.25rem 0', fontWeight: 700 }}>{value}</p>
      {sub && <p style={{ color: '#64748b', fontSize: '0.75rem', margin: 0 }}>{sub}</p>}
    </div>
  );
}

export function DashboardPage() {
  const { data: incidentList = [] } = useQuery({ queryKey: ['incidents'], queryFn: () => incidents.list({ limit: 200 }) });
  const { data: alertList = [] } = useQuery({ queryKey: ['alerts-recent'], queryFn: () => alerts.list({ limit: 20 }) });
  const { data: coverageList = [] } = useQuery({ queryKey: ['coverage'], queryFn: () => coverage.list() });

  const openIncidents = incidentList.filter((i: Incident) => i.state === 'OUVERT' || i.state === 'EN_COURS');
  const criticalIncidents = openIncidents.filter((i: Incident) => i.severity === 'CRITIQUE' || i.severity === 'ELEVE');
  const activeSources = (coverageList as CoverageState[]).filter((c) => c.state === 'ACTIVE').length;
  const silentSources = (coverageList as CoverageState[]).filter((c) => c.state === 'SILENCIEUSE' || c.state === 'FLUX_INCOMPLET').length;

  return (
    <div>
      <h1 style={{ fontSize: '1.5rem', marginBottom: '1.5rem' }}>Tableau de bord</h1>

      {/* KPIs */}
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '2rem' }}>
        <StatCard label="Incidents ouverts" value={openIncidents.length} color="#f97316" />
        <StatCard label="Critiques / Élevés" value={criticalIncidents.length} color="#ef4444" />
        <StatCard label="Alertes récentes" value={alertList.length} sub="20 dernières" />
        <StatCard label="Sources actives" value={activeSources} color="#22c55e" sub={silentSources > 0 ? `${silentSources} silencieuse(s)` : undefined} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', alignItems: 'start' }}>
        {/* Incidents ouverts */}
        <div>
          <h2 style={{ fontSize: '1rem', color: '#94a3b8', marginBottom: '0.75rem' }}>Incidents ouverts</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {openIncidents.slice(0, 10).map((inc: Incident) => (
              <a
                key={inc.id}
                href={`/incidents/${inc.id}`}
                style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', background: '#1e293b', padding: '0.75rem', borderRadius: '0.375rem', textDecoration: 'none', color: '#e2e8f0' }}
              >
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: SEVERITY_DOT[inc.severity] || '#6b7280', flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: '0.9rem' }}>{inc.title}</span>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>{inc.state}</span>
              </a>
            ))}
            {openIncidents.length === 0 && <p style={{ color: '#64748b', fontSize: '0.9rem' }}>Aucun incident ouvert</p>}
          </div>
        </div>

        {/* Couverture sources */}
        <div>
          <h2 style={{ fontSize: '1rem', color: '#94a3b8', marginBottom: '0.75rem' }}>Couverture sources</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {(coverageList as CoverageState[]).map((c) => (
              <div key={c.source_id} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', background: '#1e293b', padding: '0.75rem', borderRadius: '0.375rem' }}>
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: COVERAGE_DOT[c.state] || '#6b7280', flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: '0.9rem' }}>{c.source_name}</span>
                <span style={{ fontSize: '0.75rem', color: '#64748b' }}>{c.state}</span>
                <span style={{ fontSize: '0.75rem', color: '#475569' }}>
                  {c.last_received_at ? new Date(c.last_received_at).toLocaleTimeString('fr-FR') : '—'}
                </span>
              </div>
            ))}
            {coverageList.length === 0 && <p style={{ color: '#64748b', fontSize: '0.9rem' }}>Aucune source</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
